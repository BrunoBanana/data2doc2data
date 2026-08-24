"""Backend-only connected planner for bounded analysis-cycle decisions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable, Mapping

from .analysis_cycle import AnalysisCycle, CyclePlanError, RoundDecision, validate_round_decision


MAX_PLANNER_PROMPT_BYTES = 8_192
MAX_PLANNER_RESPONSE_BYTES = 32_768


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
    ) -> None:
        self.gateway = gateway
        self.provider = provider
        self.workspace = workspace.expanduser().resolve()
        self.registered_tools = frozenset(registered_tools)

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
            for event in self.gateway.send(self.provider, session, prompt):
                if event.kind == "approval.request":
                    raise PlannerWaiting("read-only planning cannot request approval", session.provider_session_id)
                if event.kind in {"message.delta", "plan.delta"}:
                    text = event.payload.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
                if sum(len(chunk.encode("utf-8")) for chunk in chunks) > MAX_PLANNER_RESPONSE_BYTES:
                    raise CyclePlanError("planner response is too large")
            decision = _parse_decision("".join(chunks))
            expected_round = len(cycle.rounds) + 1
            if decision.round_number != expected_round:
                raise CyclePlanError("planner decision round number does not match the cycle")
            prior = cycle.rounds[-1].decision if cycle.rounds else None
            validate_round_decision(decision, self.registered_tools, prior_decision=prior)
            if not set(decision.prior_artifact_refs) <= set(cycle.artifact_refs):
                raise CyclePlanError("planner decision references an unknown artifact")
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
        }
        contract = (
            "你是业务分析工具规划器。原始数据始终留在本机；你只会看到派生摘要。"
            "不要输出思维链，不要请求写文件、执行命令或审批。"
            "只输出一个 JSON 对象，字段必须是 round_number, action, tool, arguments, "
            "rationale_summary, prior_artifact_refs, evidence_gaps, stop_reason。"
            "action 只能是 continue 或 finish；continue 只能调用 registered_tools；"
            "第二轮以后必须引用上一轮产物；最多三轮；证据足够或没有非重复检验时 finish。\n"
        )
        payload = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        prompt = contract + payload
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
        prompt = contract + json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
