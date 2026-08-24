"""Keep loopback HTTP integration tests independent of machine proxy settings."""

from __future__ import annotations

import os


def _with_loopback_bypass(value: str | None) -> str:
    entries = [entry.strip() for entry in (value or "").split(",") if entry.strip()]
    for host in ("127.0.0.1", "localhost"):
        if host not in entries:
            entries.append(host)
    return ",".join(entries)


for _proxy_variable in ("NO_PROXY", "no_proxy"):
    os.environ[_proxy_variable] = _with_loopback_bypass(os.environ.get(_proxy_variable))
