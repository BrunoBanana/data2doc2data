"""Backend-only connected planner for bounded analysis-cycle decisions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import threading
from typing import Iterable, Mapping

from .analysis_cycle import AnalysisCycle, CyclePlanError, RoundDecision, validate_round_decision


MAX_PLANNER_PROMPT_BYTES = 8_192
MAX_PLANNER_RESPONSE_BYTES = 32_768
PLANNER_ENVELOPE_MARKER = "<analysis_envelope_json>"
TOOL_ARGUMENT_CONTRACTS: dict[str, dict[str, object]] = {
    "compare_periods": {
        "required": ["metric"],
        "optional": ["split"],
        "types": {"metric": "available metric string", "split": "integer or null"},
    },
    "detect_anomalies": {
        "required": ["metric"],
        "optional": ["window", "threshold"],
        "types": {"metric": "available metric string", "window": "integer", "threshold": "number"},
    },
    "detect_change_points": {
        "required": ["metric"],
        "optional": ["minimum_window"],
        "types": {"metric": "available metric string", "minimum_window": "integer"},
    },
    "segment_rank": {
        "required": ["metric", "dimension"],
        "optional": ["split_date", "minimum_samples"],
        "types": {
            "metric": "available metric string",
            "dimension": "available dimension string",
            "split_date": "YYYY-MM-DD string or null",
            "minimum_samples": "integer",
        },
    },
    "decompose_change": {
        "required": ["metric", "dimension"],
        "optional": ["split_date", "numerator_metric", "denominator_metric"],
        "types": {
            "metric": "available metric string",
            "dimension": "available dimension string",
            "split_date": "YYYY-MM-DD string or null",
            "numerator_metric": "available metric string or null",
            "denominator_metric": "available metric string or null",
        },
    },
    "correlate_metrics": {
        "required": ["leading_metric", "lagging_metric"],
        "optional": ["max_lag"],
        "types": {
            "leading_metric": "available metric string",
            "lagging_metric": "different available metric string",
            "max_lag": "integer",
        },
    },
    "compare_groups": {
        "required": ["metric", "dimension", "first_group", "second_group"],
        "optional": ["bootstrap_samples"],
        "types": {
            "metric": "available metric string",
            "dimension": "available dimension string",
            "first_group": "group string",
            "second_group": "different group string",
            "bootstrap_samples": "integer",
        },
    },
    "analyze_text": {
        "required": [],
        "optional": ["seed"],
        "types": {"seed": "integer"},
    },
}


class PlannerWaiting(RuntimeError):
    """Signals that the cycle should checkpoint until the provider can resume."""

    def __init__(self, message: str, provider_resume_id: str | None = None) -> None:
        super().__init__(message)
        self.provider_resume_id = provider_resume_id


@dataclass(frozen=True)
class PlannerResult:
    decision: RoundDecision
    provider_resume_id: str


class ConnectedCyclePlanner:
    def __init__(
        self,
        gateway,
        provider: str,
        workspace: Path,
        registered_tools: Iterable[str],
        *,
        turn_deadline_seconds: float = 90.0,
    ) -> None:
        if turn_deadline_seconds <= 0:
            raise ValueError("planner turn deadline must be positive")
        self.gateway = gateway
        self.provider = provider
        self.workspace = workspace.expanduser().resolve()
        self.registered_tools = frozenset(registered_tools)
        self.turn_deadline_seconds = turn_deadline_seconds
        self._repair_hint: str | None = None

    def decide(
        self,
        cycle: AnalysisCycle,
        artifact_projections: tuple[Mapping[str, object], ...],
        *,
        provider_resume_id: str | None = None,
    ) -> PlannerResult:
        session = None
        try:
            session = self.gateway.create_session(self.provider, self.workspace, resume_id=provider_resume_id)
            prompt = self._prompt(cycle, artifact_projections)
            chunks = []
            deadline_reached = threading.Event()

            def interrupt_at_deadline() -> None:
                deadline_reached.set()
                try:
                    self.gateway.interrupt(self.provider, session)
                except Exception:
                    # The deadline remains authoritative even if a failed host
                    # connection cannot acknowledge interruption.
                    pass

            watchdog = threading.Timer(self.turn_deadline_seconds, interrupt_at_deadline)
            watchdog.daemon = True
            watchdog.start()
            try:
                for event in self.gateway.send(self.provider, session, prompt):
                    if deadline_reached.is_set():
                        raise PlannerWaiting(
                            "provider planning turn exceeded its deadline",
                            session.provider_session_id,
                        )
                    if event.kind == "approval.request":
                        raise PlannerWaiting("read-only planning cannot request approval", session.provider_session_id)
                    if event.kind == "message.delta":
                        text = event.payload.get("text")
                        if isinstance(text, str):
                            chunks.append(text)
                    if sum(len(chunk.encode("utf-8")) for chunk in chunks) > MAX_PLANNER_RESPONSE_BYTES:
                        raise CyclePlanError("planner response is too large")
                if deadline_reached.is_set():
                    raise PlannerWaiting(
                        "provider planning turn exceeded its deadline",
                        session.provider_session_id,
                    )
            finally:
                watchdog.cancel()
            try:
                decision = _parse_decision("".join(chunks))
                expected_round = len(cycle.rounds) + 1
                if decision.round_number != expected_round:
                    raise CyclePlanError("planner decision round number does not match the cycle")
                prior = cycle.rounds[-1].decision if cycle.rounds else None
                validate_round_decision(decision, self.registered_tools, prior_decision=prior)
                if not set(decision.prior_artifact_refs) <= set(cycle.artifact_refs):
                    raise CyclePlanError("planner decision references an unknown artifact")
            except CyclePlanError as exc:
                self._repair_hint = str(exc)[:300]
                raise PlannerWaiting(
                    "provider did not return a valid public decision",
                    None,
                ) from exc
            self._repair_hint = None
            return PlannerResult(decision, session.provider_session_id)
        except (CyclePlanError, PlannerWaiting):
            raise
        except Exception as exc:
            resume_id = session.provider_session_id if session is not None else provider_resume_id
            raise PlannerWaiting(f"provider planning is waiting: {type(exc).__name__}", resume_id) from exc

    def _prompt(
        self,
        cycle: AnalysisCycle,
        artifact_projections: tuple[Mapping[str, object], ...],
    ) -> str:
        envelope = {
            "cycle": {
                "cycle_id": cycle.cycle_id,
                "next_round": len(cycle.rounds) + 1,
                "max_rounds": cycle.max_rounds,
                "prior_rounds": [
                    {
                        "round_number": item.round_number,
                        "tool": item.decision.tool,
                        "arguments": _safe_value(item.decision.arguments),
                        "artifact_refs": list(item.artifact_refs),
                    }
                    for item in cycle.rounds
                ],
            },
            "artifacts": [_safe_value(item) for item in artifact_projections[:20]],
            "registered_tools": sorted(self.registered_tools),
            "allowed_prior_artifact_refs": list(cycle.artifact_refs),
            "tool_contracts": {
                name: TOOL_ARGUMENT_CONTRACTS[name]
                for name in sorted(self.registered_tools)
                if name in TOOL_ARGUMENT_CONTRACTS
            },
        }
        contract = (
            "你是业务分析工具规划器。原始数据始终留在本机；你只会看到派生摘要。"
            "不要输出思维链，不要请求写文件、执行命令或审批。"
            "只输出一个 JSON 对象，字段必须是 round_number, action, tool, arguments, "
            "rationale_summary, prior_artifact_refs, evidence_gaps, stop_reason。"
            "action 只能是 continue 或 finish；continue 只能调用 registered_tools；"
            "continue 时 stop_reason 必须为 null；finish 时 tool 必须为 null 且 arguments 必须为 {}；"
            "第二轮以后必须引用上一轮产物；最多三轮；证据足够或没有非重复检验时 finish。\n"
            "arguments 只能包含 tool_contracts 对应工具声明的参数，并遵守 types；"
            "evidence_gaps 必须是 JSON 数组，没有缺口时输出 []，有缺口时每项只能包含 "
            "gap_id, description, suggested_tool；prior_artifact_refs 必须是 JSON 字符串数组，"
            "且只能引用 allowed_prior_artifact_refs；第一轮该数组为空时必须输出 []。\n"
        )
        if self._repair_hint is not None:
            contract += (
                "上一份公开决策未通过验证："
                + self._repair_hint
                + "。请根据同一输入重新生成完整 JSON 对象，不要解释。\n"
            )
        payload = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        prompt = contract + PLANNER_ENVELOPE_MARKER + "\n" + payload
        if len(prompt.encode("utf-8")) <= MAX_PLANNER_PROMPT_BYTES:
            return prompt
        envelope["artifacts"] = [
            {
                "tool": item.get("tool"),
                "status": item.get("status"),
                "artifact_refs": item.get("artifact_refs", []),
                "summary": {"truncated": True},
            }
            for item in envelope["artifacts"][:10]
            if isinstance(item, dict)
        ]
        prompt = (
            contract
            + PLANNER_ENVELOPE_MARKER
            + "\n"
            + json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        if len(prompt.encode("utf-8")) > MAX_PLANNER_PROMPT_BYTES:
            raise CyclePlanError("planner prompt cannot fit the bounded envelope")
        return prompt


def _parse_decision(text: str) -> RoundDecision:
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise CyclePlanError("planner must return one JSON decision object") from exc
    if not isinstance(payload, Mapping):
        raise CyclePlanError("planner decision must be an object")
    required = {
        "round_number",
        "action",
        "tool",
        "arguments",
        "rationale_summary",
        "prior_artifact_refs",
        "evidence_gaps",
        "stop_reason",
    }
    if set(payload) != required:
        raise CyclePlanError("planner decision fields do not match the contract")
    return RoundDecision.from_dict(payload)


def _safe_value(value: object) -> object:
    forbidden = {"raw", "raw_data", "raw_rows", "row", "rows", "records", "path", "paths"}
    if isinstance(value, Mapping):
        return {
            str(key): _safe_value(item)
            for key, item in value.items()
            if str(key).lower() not in forbidden
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:100]]
    if isinstance(value, str):
        if value.startswith(("/", "~/")) or ":\\" in value:
            return "[local reference omitted]"
        return value[:1_000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:500]
