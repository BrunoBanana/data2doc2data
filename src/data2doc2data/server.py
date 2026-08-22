"""Loopback-only HTTP companion for local workspace setup and analysis."""

from __future__ import annotations

import base64
import binascii
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agent_api import AgentApiError, AgentWebService, BROWSER_SESSION_SECONDS, TERMINAL_EVENTS
from .agents.gateway import AgentGateway, AgentGatewayError
from .analysis import InputValidationError, analyze, load_profile_ruleset, validate_profile
from .config import Profile, ProfileError, ProfileStore
from .demo_scenarios import DemoScenarioCatalog, DemoScenarioError
from .evidence_context import build_source_profile
from .ingestion import (
    MAX_SOURCE_BYTES,
    IngestionError,
    IngestionPlan,
    apply_plan,
    build_proposal_prompt,
    fetch_api_snapshot,
    parse_plan_response,
    preview_source,
    suggest_plan,
    write_standard_csv,
)
from .sessions import AuditStore, SessionStore


STATIC_ROOT = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BYTES = 8_000_000
SESSION_EVENTS_ROUTE = re.compile(r"/api/agent-sessions/([A-Za-z0-9._:-]{1,200})/events")
SESSION_MESSAGES_ROUTE = re.compile(r"/api/agent-sessions/([A-Za-z0-9._:-]{1,200})/messages")
SESSION_INTERRUPT_ROUTE = re.compile(r"/api/agent-sessions/([A-Za-z0-9._:-]{1,200})/interrupt")
SESSION_APPROVAL_ROUTE = re.compile(
    r"/api/agent-sessions/([A-Za-z0-9._:-]{1,200})/approvals/([A-Za-z0-9._:-]{1,200})"
)
INGEST_MUTATION_ROUTES = frozenset(
    {
        "/api/ingest/upload",
        "/api/ingest/preview",
        "/api/ingest/apply",
        "/api/ingest/api-snapshot",
        "/api/ingest/propose",
    }
)


class CompanionHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_close(self) -> None:
        if not getattr(self, "_agent_service_closed", False):
            self._agent_service_closed = True
            try:
                self.agent_service.close()
            finally:
                super().server_close()
            return
        super().server_close()


def create_server(
    store: ProfileStore,
    host: str = "127.0.0.1",
    port: int = 8765,
    gateway: AgentGateway | None = None,
    agent_workspace: Path | None = None,
    session_store: SessionStore | None = None,
    audit_store: AuditStore | None = None,
) -> ThreadingHTTPServer:
    """Create a server that is restricted to the IPv4 loopback interface."""
    if host != "127.0.0.1":
        raise ValueError("host must be the loopback address 127.0.0.1")
    workspace = (agent_workspace or Path.cwd()).expanduser().resolve()
    state_directory = store.path.parent
    agent_service = AgentWebService(
        gateway or AgentGateway({}),
        workspace,
        session_store or SessionStore(state_directory / "agent-sessions.json"),
        audit_store or AuditStore(state_directory / "agent-audit.jsonl"),
        store,
    )
    server = CompanionHTTPServer((host, port), CompanionHandler)
    server.profile_store = store
    server.agent_service = agent_service
    return server


def _ingest_output_dir(store: ProfileStore) -> Path:
    """Persist ingested artifacts under the state directory, never in shared spots."""
    return store.path.parent / "ingested"


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return cleaned[:120] or "upload"


def ingest_upload(filename: str, content_b64: str, store: ProfileStore) -> dict[str, object]:
    """Accept a base64-encoded local file and store it for later ingestion."""
    if not isinstance(filename, str) or not filename:
        raise ValueError("filename is required")
    if not isinstance(content_b64, str) or not content_b64:
        raise ValueError("file content is required")
    try:
        raw = base64.b64decode(content_b64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("file content must be base64-encoded") from error
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("file exceeds the local processing size limit")
    target_dir = _ingest_output_dir(store) / "uploads"
    target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = target_dir / _safe_filename(Path(filename).name)
    target.write_bytes(raw)
    return {"path": str(target), "filename": target.name}


def ingest_preview(
    path: str,
    use_agent: bool = False,
    gateway: AgentGateway | None = None,
    workspace: Path | None = None,
    validate_local: bool = False,
) -> dict[str, object]:
    """Probe a local source file and suggest a built-in field mapping.

    With ``use_agent=True`` the preview also asks a ready local agent to propose
    a mapping (returned as ``agent_plan``) without blocking the caller when no
    agent is available. ``validate_local=True`` enforces stricter checks for a
    user-supplied absolute path (exists, regular file, within the size limit).
    """
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    if validate_local:
        _validate_local_source_path(path)
    preview = preview_source(Path(path))
    suggestion = suggest_plan(preview)
    result: dict[str, object] = {
        "preview": preview.to_dict(),
        "suggestion": suggestion.to_dict() if suggestion else None,
    }
    if use_agent:
        agent_plan, _reason = _agent_plan_for(preview, path, gateway, workspace)
        if agent_plan is not None:
            result["agent_plan"] = agent_plan.to_dict()
            result["agent_used"] = True
    return result


def ingest_apply(
    path: str,
    plan: dict,
    store: ProfileStore,
    mode: str,
    knowledge_path: str | None = None,
    api_config: dict | None = None,
) -> dict[str, object]:
    """Convert a source under a confirmed plan and point the profile at the result.

    Beyond the standard CSV output, this captures the ingestion provenance
    (source + plan) and, for API mode, the endpoint config, so a later snapshot
    refresh or audit can reproduce how the deterministic dataset was built.
    """
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    if not isinstance(plan, dict):
        raise ValueError("plan is required")
    parsed_plan = IngestionPlan.from_dict(plan)
    result = apply_plan(Path(path), parsed_plan)
    output_dir = _ingest_output_dir(store)
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    output = output_dir / f"{Path(path).stem}.standard.csv"
    write_standard_csv(result.rows, output)
    profile = store.load() or Profile.demo()
    resolved_mode = mode or profile.mode
    resolved_knowledge = (knowledge_path or "").strip() or profile.knowledge_path
    knowledge_warning = _validate_knowledge_path(resolved_knowledge)
    ingestion_config: dict[str, object] = {
        "source_path": path,
        "plan": parsed_plan.to_dict(),
        "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    api_blob = api_config if resolved_mode == "api" else profile.api
    if api_blob is not None and not isinstance(api_blob, dict):
        api_blob = None
    new_profile = Profile(
        mode=resolved_mode,
        data_path=str(output),
        knowledge_path=resolved_knowledge,
        demo_scenario=profile.demo_scenario,
        rules_path=profile.rules_path,
        ingestion=ingestion_config,
        api=api_blob,
    )
    store.save(new_profile)
    return {
        "result": result.to_dict(),
        "profile": new_profile.to_dict(),
        "needs_knowledge_path": not resolved_knowledge,
        "knowledge_warning": knowledge_warning,
    }


def _validate_knowledge_path(path: str) -> str | None:
    """Return a warning if the knowledge directory looks unusable, else None."""
    if not path:
        return None
    candidate = Path(path).expanduser()
    if not candidate.is_dir():
        return "文档目录不存在，确定性结论可能缺少证据来源。"
    documents = [
        child for child in candidate.iterdir()
        if child.is_file() and child.suffix.lower() in {".md", ".txt"}
    ]
    if not documents:
        return "文档目录中没有 .md/.txt 文档，确定性结论可能缺少证据来源。"
    return None


def _agent_plan_for(
    preview: object,
    path: str,
    gateway: AgentGateway | None,
    workspace: Path | None,
) -> tuple[IngestionPlan | None, str | None]:
    """Ask a ready local agent for a field mapping; return (plan, reason) where reason is set on failure."""
    provider = _first_ready_provider(gateway)
    if provider is None:
        return None, "没有可用的本地助手，已使用内置建议。"
    try:
        gateway.connect(provider)
        session = gateway.create_session(provider, workspace)
        prompt = build_proposal_prompt(preview, path)
        collected: list[str] = []
        for event in gateway.send(provider, session, prompt):
            if event.kind == "message.delta":
                collected.append(str(event.payload.get("text", "")))
            elif event.kind in {"turn.error", "provider.error"}:
                return None, "助手推断失败，已使用内置建议。"
        return parse_plan_response("".join(collected)), None
    except AgentGatewayError:
        return None, "助手推断失败，已使用内置建议。"


def ingest_propose(
    path: str,
    gateway: AgentGateway | None,
    workspace: Path,
) -> dict[str, object]:
    """Propose a field mapping, preferring an in-the-loop local agent over the built-in heuristic.

    The agent only interprets the already-probed structure (field names + sample
    rows); it never sees the raw file. When no agent is available the call degrades
    to the built-in suggestion so the user is never blocked.
    """
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    preview = preview_source(Path(path))
    builtin = suggest_plan(preview)
    agent_plan, reason = _agent_plan_for(preview, path, gateway, workspace)
    return {
        "preview": preview.to_dict(),
        "suggestion": builtin.to_dict() if builtin else None,
        "agent_plan": agent_plan.to_dict() if agent_plan else None,
        "agent_used": agent_plan is not None,
        "reason": None if agent_plan is not None else reason,
    }


def _first_ready_provider(gateway: AgentGateway | None) -> str | None:
    """Return the first provider that is installed, authenticated and compatible."""
    if gateway is None:
        return None
    for name in gateway.provider_names:
        try:
            status = gateway.detect(name)
        except AgentGatewayError:
            continue
        if status.available and status.authenticated and status.compatible:
            return name
    return None


def _validate_local_source_path(path: str) -> None:
    """Validate a user-supplied absolute path before ingestion."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValueError("请提供本机上的绝对路径（如 /Users/name/data.xlsx）。")
    if not candidate.exists():
        raise ValueError("该路径不存在，请确认后重试。")
    if not candidate.is_file():
        raise ValueError("该路径不是文件，请选择数据文件。")
    try:
        size = candidate.stat().st_size
    except OSError as error:
        raise ValueError(f"无法读取文件大小：{error}") from error
    if size > MAX_SOURCE_BYTES:
        raise ValueError("文件超过本地处理大小上限，请用较小的文件或拆分后上传。")


def ingest_api_snapshot(
    url: str,
    store: ProfileStore,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    use_agent: bool = False,
    gateway: AgentGateway | None = None,
    workspace: Path | None = None,
) -> dict[str, object]:
    """Fetch an HTTPS API into a local snapshot, then preview it like any file."""
    if not isinstance(url, str) or not url:
        raise ValueError("url is required")
    snapshot_dir = _ingest_output_dir(store) / "api"
    snapshot = fetch_api_snapshot(url, snapshot_dir, headers, params)
    preview = preview_source(snapshot.path)
    suggestion = suggest_plan(preview)
    result: dict[str, object] = {
        "snapshot": {
            "path": str(snapshot.path),
            "fetched_at": snapshot.fetched_at,
            "content_type": snapshot.content_type,
        },
        "preview": preview.to_dict(),
        "suggestion": suggestion.to_dict() if suggestion else None,
    }
    if use_agent:
        agent_plan, _reason = _agent_plan_for(preview, str(snapshot.path), gateway, workspace)
        if agent_plan is not None:
            result["agent_plan"] = agent_plan.to_dict()
            result["agent_used"] = True
    return result
class CompanionHandler(BaseHTTPRequestHandler):
    server: ThreadingHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - HTTP method naming is conventional.
        if not self._allow_local_origin():
            return
        path = urlparse(self.path).path
        if path == "/api/agents":
            browser_session, csrf_token = self._agents().browser_sessions.issue()
            self._send_json(
                HTTPStatus.OK,
                {"agents": self._agents().list_agents(), "csrf_token": csrf_token},
                {
                    "Set-Cookie": (
                        f"d2d2d_session={browser_session}; Path=/; Max-Age={BROWSER_SESSION_SECONDS}; "
                        "HttpOnly; SameSite=Strict"
                    )
                },
            )
            return
        events_match = SESSION_EVENTS_ROUTE.fullmatch(path)
        if events_match:
            try:
                owner_id = self._agents().browser_sessions.authorize(self.headers.get("Cookie"))
                event_buffer = self._agents().event_buffer(owner_id, events_match.group(1))
                query = parse_qs(urlparse(self.path).query)
                try:
                    after_event_id = max(0, int(query.get("after", ["0"])[0]))
                except (TypeError, ValueError):
                    after_event_id = 0
                self._send_events(event_buffer, after_event_id)
            except AgentApiError as error:
                self._send_json(error.status, {"error": str(error)})
            return
        if path == "/api/profile":
            try:
                profile = self._store().load()
            except ProfileError as error:
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
                return
            self._send_json(
                HTTPStatus.OK,
                {"configured": profile is not None, "profile": profile.to_dict() if profile else None},
            )
            return
        if path == "/api/source-profile":
            try:
                profile = self._store().load() or Profile.demo()
                source_profile = build_source_profile(profile)
            except (InputValidationError, ProfileError) as error:
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
                return
            self._send_json(HTTPStatus.OK, source_profile.to_dict())
            return
        if path == "/api/demo-scenarios":
            try:
                catalog = DemoScenarioCatalog.load()
            except DemoScenarioError:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "demo scenario catalog is unavailable"},
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "default": catalog.default.id,
                    "scenarios": [scenario.to_dict() for scenario in catalog.list()],
                },
            )
            return
        self._serve_static(path)

    def do_PUT(self) -> None:  # noqa: N802 - HTTP method naming is conventional.
        if not self._allow_local_origin():
            return
        if urlparse(self.path).path != "/api/profile":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
            return
        try:
            profile = Profile.from_dict(self._read_json())
            validate_profile(profile)
            self._store().save(profile)
            self._agents().invalidate_analysis()
        except (InputValidationError, ProfileError, ValueError) as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
            return
        self._send_json(HTTPStatus.OK, {"configured": True, "profile": profile.to_dict()})

    def do_POST(self) -> None:  # noqa: N802 - HTTP method naming is conventional.
        if not self._allow_local_origin():
            return
        path = urlparse(self.path).path
        if path == "/api/agent-sessions":
            self._create_agent_session()
            return
        messages_match = SESSION_MESSAGES_ROUTE.fullmatch(path)
        if messages_match:
            self._start_agent_turn(messages_match.group(1))
            return
        approval_match = SESSION_APPROVAL_ROUTE.fullmatch(path)
        if approval_match:
            self._decide_agent_approval(approval_match.group(1), approval_match.group(2))
            return
        interrupt_match = SESSION_INTERRUPT_ROUTE.fullmatch(path)
        if interrupt_match:
            self._interrupt_agent(interrupt_match.group(1))
            return
        if path in INGEST_MUTATION_ROUTES:
            try:
                self._authorize_agent_mutation()
            except AgentApiError as error:
                self._send_json(error.status, {"error": str(error)})
                return
        if path == "/api/ingest/upload":
            self._ingest_upload()
            return
        if path == "/api/ingest/preview":
            self._ingest_preview()
            return
        if path == "/api/ingest/apply":
            self._ingest_apply()
            return
        if path == "/api/ingest/api-snapshot":
            self._ingest_api_snapshot()
            return
        if path == "/api/ingest/propose":
            self._ingest_propose()
            return
        if path != "/api/analyze":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
            return
        try:
            payload = self._read_json()
            question = payload.get("question", "") if isinstance(payload, dict) else ""
            metric_override = payload.get("metric_override") if isinstance(payload, dict) else None
            profile = self._store().load() or Profile.demo()
            result = analyze(
                question,
                profile,
                metric_override,
                self._store().index_cache_path,
                load_profile_ruleset(profile),
            )
            owner_id = self._optional_agent_owner()
            if owner_id is not None:
                self._agents().record_analysis(owner_id, result, profile)
            self._send_json(HTTPStatus.OK, result.to_dict())
        except (InputValidationError, ProfileError, ValueError) as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

    def _create_agent_session(self) -> None:
        try:
            owner_id = self._authorize_agent_mutation()
            session = self._agents().create_session(owner_id, self._read_json())
            self._send_json(HTTPStatus.CREATED, {"session": session})
        except AgentApiError as error:
            self._send_json(error.status, {"error": str(error)})
        except ValueError as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

    def _start_agent_turn(self, session_id: str) -> None:
        try:
            owner_id = self._authorize_agent_mutation()
            self._agents().start_turn(owner_id, session_id, self._read_json())
            self._send_json(HTTPStatus.ACCEPTED, {"accepted": True})
        except AgentApiError as error:
            self._send_json(error.status, {"error": str(error)})
        except ValueError as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

    def _decide_agent_approval(self, session_id: str, approval_id: str) -> None:
        try:
            owner_id = self._authorize_agent_mutation()
            self._agents().decide_approval(owner_id, session_id, approval_id, self._read_json())
            self._send_json(HTTPStatus.OK, {"accepted": True})
        except AgentApiError as error:
            self._send_json(error.status, {"error": str(error)})
        except ValueError as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

    def _interrupt_agent(self, session_id: str) -> None:
        try:
            owner_id = self._authorize_agent_mutation()
            payload = self._read_json()
            if not isinstance(payload, dict):
                raise ValueError("interrupt request must be an object")
            self._agents().interrupt(owner_id, session_id)
            self._send_json(HTTPStatus.ACCEPTED, {"accepted": True})
        except AgentApiError as error:
            self._send_json(error.status, {"error": str(error)})
        except ValueError as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

    def _ingest_upload(self) -> None:
        try:
            payload = self._read_json()
            if not isinstance(payload, dict):
                raise ValueError("request must be an object")
            result = ingest_upload(
                payload.get("filename", ""),
                payload.get("content", ""),
                self._store(),
            )
            self._send_json(HTTPStatus.OK, result)
        except (ValueError, IngestionError) as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

    def _ingest_preview(self) -> None:
        try:
            payload = self._read_json()
            if not isinstance(payload, dict):
                raise ValueError("request must be an object")
            result = ingest_preview(
                payload.get("path", ""),
                use_agent=bool(payload.get("use_agent", False)),
                gateway=self._agents().gateway,
                workspace=self._agents().workspace,
                validate_local=bool(payload.get("validate_local", False)),
            )
            self._send_json(HTTPStatus.OK, result)
        except (ValueError, IngestionError) as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

    def _ingest_apply(self) -> None:
        try:
            payload = self._read_json()
            if not isinstance(payload, dict):
                raise ValueError("request must be an object")
            result = ingest_apply(
                payload.get("path", ""),
                payload.get("plan", {}),
                self._store(),
                payload.get("mode", "local"),
                payload.get("knowledge_path"),
                payload.get("api_config"),
            )
            self._send_json(HTTPStatus.OK, result)
        except (ValueError, IngestionError) as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

    def _ingest_propose(self) -> None:
        try:
            payload = self._read_json()
            if not isinstance(payload, dict):
                raise ValueError("request must be an object")
            result = ingest_propose(
                payload.get("path", ""),
                self._agents().gateway,
                self._agents().workspace,
            )
            self._send_json(HTTPStatus.OK, result)
        except (ValueError, IngestionError) as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

    def _ingest_api_snapshot(self) -> None:
        try:
            payload = self._read_json()
            if not isinstance(payload, dict):
                raise ValueError("request must be an object")
            headers = payload.get("headers")
            params = payload.get("params")
            if headers is not None and not isinstance(headers, dict):
                raise ValueError("headers must be an object")
            if params is not None and not isinstance(params, dict):
                raise ValueError("params must be an object")
            result = ingest_api_snapshot(
                payload.get("url", ""),
                self._store(),
                headers,
                params,
                use_agent=bool(payload.get("use_agent", False)),
                gateway=self._agents().gateway,
                workspace=self._agents().workspace,
            )
            self._send_json(HTTPStatus.OK, result)
        except (ValueError, IngestionError) as error:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

    def do_OPTIONS(self) -> None:  # noqa: N802 - HTTP method naming is conventional.
        if not self._allow_local_origin():
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, PUT, OPTIONS")
        self._send_security_headers()
        self.end_headers()

    def _store(self) -> ProfileStore:
        return self.server.profile_store

    def _agents(self) -> AgentWebService:
        return self.server.agent_service

    def _authorize_agent_mutation(self) -> str:
        return self._agents().browser_sessions.authorize_mutation(
            self.headers.get("Cookie"),
            self.headers.get("X-CSRF-Token"),
        )

    def _optional_agent_owner(self) -> str | None:
        try:
            return self._agents().browser_sessions.authorize(self.headers.get("Cookie"))
        except AgentApiError:
            return None

    def _allow_local_origin(self) -> bool:
        expected_host = f"127.0.0.1:{self.server.server_port}"
        origin = self.headers.get("Origin")
        if self.headers.get("Host") == expected_host and origin in {None, f"http://{expected_host}"}:
            return True
        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "request must originate from the local companion"})
        return False

    def _read_json(self) -> object:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("request body is required")
        if length > MAX_REQUEST_BYTES:
            raise ValueError("request body is too large")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("request body must be JSON") from error

    def _serve_static(self, path: str) -> None:
        requested = "index.html" if path in {"/", "/index.html"} else path.lstrip("/")
        allowed = {
            "index.html",
            "app.css",
            "app.js",
            "state.js",
            "ui.js",
            "api.js",
            "pipeline.js",
            "data-panel.js",
            "ingest-panel.js",
            "assistant-panel.js",
            "favicon.svg",
        }
        if requested not in allowed:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
            return
        asset = STATIC_ROOT / requested
        if not asset.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "setup page is unavailable"})
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }[asset.suffix]
        payload = asset.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(
        self,
        status: HTTPStatus,
        payload: object,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(data)

    def _send_events(self, event_buffer, after_event_id: int = 0) -> None:
        try:
            last_event_id = max(
                after_event_id,
                int(self.headers.get("Last-Event-ID", "0")),
            )
        except ValueError:
            last_event_id = 0
        if last_event_id < 0:
            last_event_id = 0
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "close")
        self._send_security_headers()
        self.end_headers()
        self.close_connection = True
        try:
            while True:
                available = event_buffer.after(last_event_id, timeout=15.0)
                if not available:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                for event_id, event in available:
                    data = json.dumps(
                        {"kind": event.kind, "payload": event.payload},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    self.wfile.write(f"id: {event_id}\n".encode("ascii"))
                    self.wfile.write(b"data: " + data + b"\n\n")
                    self.wfile.flush()
                    last_event_id = event_id
                    if event.kind in TERMINAL_EVENTS:
                        return
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_security_headers(self) -> None:
        self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; form-action 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def log_message(self, format: str, *args: object) -> None:
        return
