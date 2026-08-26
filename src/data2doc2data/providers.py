"""Unified, redacted connection metadata for local CLIs and model APIs."""

from __future__ import annotations

import os
import re
from typing import Mapping
from urllib.parse import urlsplit

from .agents.gateway import AgentGateway, AgentGatewayError


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
_ENV_REF = re.compile(r"^env:([A-Z_][A-Z0-9_]*)$")
_KEYCHAIN_REF = re.compile(r"^keychain:([^/:\s]{1,100})/([^\s]{1,100})$")


class ProviderRegistryError(ValueError):
    pass


class ProviderRegistry:
    def __init__(self, gateway: AgentGateway, environ: Mapping[str, str] | None = None) -> None:
        self.gateway = gateway
        self.environ = os.environ if environ is None else environ
        self._api_connections: dict[str, dict[str, object]] = {}

    def list_connections(self) -> list[dict[str, object]]:
        connections = [self._local_connection(name) for name in self.gateway.provider_names]
        connections.extend(self._api_connections[key] for key in sorted(self._api_connections))
        connections.append(
            {
                "provider_id": "none",
                "kind": "none",
                "state": "available",
                "capabilities": ["deterministic_dashboard"],
                "detail": "无需模型即可使用本地确定性分析。",
                "reconnect_hint": None,
                "config": {},
            }
        )
        return connections

    def configure_openai_compatible(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ProviderRegistryError("provider configuration must be an object")
        provider_id = payload.get("provider_id")
        base_url = payload.get("base_url")
        model = payload.get("model")
        secret_ref = payload.get("secret_ref")
        if not isinstance(provider_id, str) or not _ID.fullmatch(provider_id) or provider_id == "none":
            raise ProviderRegistryError("provider_id is invalid")
        if not isinstance(model, str) or not model.strip() or len(model) > 200:
            raise ProviderRegistryError("model is required")
        _validate_base_url(base_url)
        if not isinstance(secret_ref, str) or not (_ENV_REF.fullmatch(secret_ref) or _KEYCHAIN_REF.fullmatch(secret_ref)):
            raise ProviderRegistryError("secret must be an env:NAME or keychain:service/account reference")
        env_match = _ENV_REF.fullmatch(secret_ref)
        env_available = bool(env_match and self.environ.get(env_match.group(1)))
        keychain_configured = bool(_KEYCHAIN_REF.fullmatch(secret_ref))
        state = "ready" if env_available else "configured" if keychain_configured else "auth_required"
        connection = {
            "provider_id": provider_id,
            "kind": "openai_compatible",
            "state": state,
            "capabilities": ["streaming", "bounded_context"],
            "detail": None if env_available else "已保存钥匙串引用。" if keychain_configured else "密钥引用当前不可用。",
            "reconnect_hint": None if state != "auth_required" else "请设置对应环境变量或更新系统钥匙串引用。",
            "config": {"base_url": base_url, "model": model.strip(), "secret_ref": secret_ref},
        }
        self._api_connections[provider_id] = connection
        return dict(connection)

    def skip(self) -> dict[str, object]:
        return {
            "provider_id": "none",
            "kind": "none",
            "state": "skipped",
            "capabilities": ["deterministic_dashboard"],
            "detail": "已跳过模型连接。",
            "reconnect_hint": None,
            "config": {},
        }

    def _local_connection(self, name: str) -> dict[str, object]:
        try:
            status = self.gateway.detect(name)
            if not status.available:
                state = "unavailable"
                hint = "请先安装本地 CLI。"
            elif not status.authenticated:
                state = "auth_required"
                hint = "授权已失效或尚未登录，请在终端重新登录后重试。"
            elif not status.compatible:
                state = "incompatible"
                hint = "请升级本地 CLI 到兼容版本。"
            else:
                state = "connected" if status.connected else "ready"
                hint = None
            detail = _redact_detail(status.detail)
            version = status.version
        except AgentGatewayError:
            state, hint, detail, version = "unavailable", "请检查本地 CLI 后重试。", "状态检测失败。", None
        return {
            "provider_id": name,
            "kind": "local_cli",
            "state": state,
            "capabilities": ["streaming", "approvals", "interrupt", "bounded_context"],
            "version": version,
            "detail": detail,
            "reconnect_hint": hint,
            "config": {},
        }


def _validate_base_url(value: object) -> None:
    if not isinstance(value, str) or len(value) > 2000:
        raise ProviderRegistryError("base_url is invalid")
    parsed = urlsplit(value)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if not parsed.hostname or parsed.username or parsed.password or (parsed.scheme != "https" and not (parsed.scheme == "http" and loopback)):
        raise ProviderRegistryError("base_url must use HTTPS or loopback HTTP without credentials")


def _redact_detail(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = re.sub(r"(?i)(api[_-]?key|token|secret|bearer)\s*[=:]?\s*\S+", r"\1=[REDACTED]", value)
    return redacted[:500]
