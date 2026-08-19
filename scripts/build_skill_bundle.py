"""Build a deterministic ZIP suitable for a SkillHub-style upload."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("README.md", "SKILL.md", "pyproject.toml")
PUBLIC_RESOURCE_FILES = (
    "agents/openai.yaml",
    "references/connector-guide.md",
    "src/data2doc2data/__init__.py",
    "src/data2doc2data/agent_api.py",
    "src/data2doc2data/agents/__init__.py",
    "src/data2doc2data/agents/_shared.py",
    "src/data2doc2data/agents/base.py",
    "src/data2doc2data/agents/codex.py",
    "src/data2doc2data/agents/gateway.py",
    "src/data2doc2data/agents/workbuddy.py",
    "src/data2doc2data/analysis.py",
    "src/data2doc2data/cli.py",
    "src/data2doc2data/config.py",
    "src/data2doc2data/demo_scenarios.py",
    "src/data2doc2data/evidence_context.py",
    "src/data2doc2data/hypotheses.py",
    "src/data2doc2data/mcp_server.py",
    "src/data2doc2data/metrics.py",
    "src/data2doc2data/permissions.py",
    "src/data2doc2data/provenance.py",
    "src/data2doc2data/retrieval.py",
    "src/data2doc2data/rules.py",
    "src/data2doc2data/server.py",
    "src/data2doc2data/sessions.py",
    "src/data2doc2data/sample/scenarios/catalog.json",
    "src/data2doc2data/sample/scenarios/growth-quality-alert/metrics.csv",
    "src/data2doc2data/sample/scenarios/growth-quality-alert/strategy.md",
    "src/data2doc2data/sample/scenarios/strategy-data-conflict/metrics.csv",
    "src/data2doc2data/sample/scenarios/strategy-data-conflict/strategy.md",
    "src/data2doc2data/sample/scenarios/insufficient-evidence/metrics.csv",
    "src/data2doc2data/sample/scenarios/insufficient-evidence/strategy.md",
    "src/data2doc2data/static/api.js",
    "src/data2doc2data/static/app.css",
    "src/data2doc2data/static/app.js",
    "src/data2doc2data/static/assistant-panel.js",
    "src/data2doc2data/static/data-panel.js",
    "src/data2doc2data/static/favicon.svg",
    "src/data2doc2data/static/ingest-panel.js",
    "src/data2doc2data/static/index.html",
    "src/data2doc2data/static/pipeline.js",
    "src/data2doc2data/static/state.js",
    "src/data2doc2data/static/ui.js",
)
SKILLHUB_METADATA = (
    ("slug", "data2doc2data"),
    ("version", "3.0.0"),
    ("displayName", "Data2Doc2Data-面向真实业务的数据+文本循环推理架构"),
    ("summary", "面向真实业务场景，让数据指标与策略、决策文档形成可验证的循环推理。"),
    ("tags", "[analytics, local-first, evidence]"),
    ("license", "MIT"),
)
FORBIDDEN_PRIVATE_MARKERS = (
    "private" + "-data-platform",
    "internal" + "-domain",
    "internal" + "-org",
    "internal" + "-agent-platform",
)
SENSITIVE_PUBLIC_PATTERNS = (
    re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:gh[pousr]_[a-z0-9_]{20,}|github_pat_[a-z0-9_]{20,})\b", re.IGNORECASE),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b"),
)


def bundle_files(root: Path = ROOT) -> list[Path]:
    """Return the public Skill files in a stable order."""
    files = []
    for name in ROOT_FILES:
        path = root / name
        if path.is_symlink():
            raise ValueError(f"public bundle refuses a symbolic link at {name}")
        files.append(path)
    license_path = root / "LICENSE"
    if _is_public_regular_file(license_path, root):
        files.append(license_path)
    files.extend(
        root / relative_path
        for relative_path in PUBLIC_RESOURCE_FILES
        if _is_public_regular_file(root / relative_path, root)
    )
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _is_public_regular_file(path: Path, root: Path) -> bool:
    if path.is_symlink():
        relative_path = path.relative_to(root).as_posix()
        raise ValueError(f"public bundle refuses a symbolic link at {relative_path}")
    return path.is_file()


def _validate_public_contents(files: list[Path], root: Path) -> None:
    for path in files:
        content = path.read_text(encoding="utf-8")
        normalized_content = content.lower()
        for marker in FORBIDDEN_PRIVATE_MARKERS:
            if marker in normalized_content:
                relative_path = path.relative_to(root).as_posix()
                raise ValueError(f"public bundle contains a private marker in {relative_path}")
        if any(pattern.search(content) for pattern in SENSITIVE_PUBLIC_PATTERNS):
            relative_path = path.relative_to(root).as_posix()
            raise ValueError(f"public bundle contains sensitive data in {relative_path}")


def _render_skillhub_contract(skill_md: Path) -> bytes:
    """Add platform-only metadata without changing the source Skill contract."""
    source = skill_md.read_text(encoding="utf-8")
    separator = "\n---\n"
    if not source.startswith("---\n"):
        raise ValueError("SKILL.md must begin with YAML frontmatter")
    frontmatter_end = source.find(separator, len("---\n"))
    if frontmatter_end < 0:
        raise ValueError("SKILL.md must close its YAML frontmatter")

    source_frontmatter = source[len("---\n"):frontmatter_end]
    platform_frontmatter = "\n".join(f"{key}: {value}" for key, value in SKILLHUB_METADATA)
    body = source[frontmatter_end + len(separator):]
    return f"---\n{source_frontmatter}\n{platform_frontmatter}\n---\n{body}".encode("utf-8")


def _bundle_content(path: Path, root: Path) -> bytes:
    if path.relative_to(root).as_posix() == "SKILL.md":
        return _render_skillhub_contract(path)
    return path.read_bytes()


def build_bundle(output: Path, root: Path = ROOT, draft: bool = False) -> Path:
    """Write the public Skill contract and local runtime into ``output``."""
    output = output.expanduser()
    if not draft and not (root / "LICENSE").is_file():
        raise ValueError("LICENSE is required for a public SkillHub bundle")
    files = bundle_files(root)
    _validate_public_contents(files, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative_path = path.relative_to(root).as_posix()
            archive_path = "LICENSE.md" if relative_path == "LICENSE" else relative_path
            entry = zipfile.ZipInfo(archive_path, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, _bundle_content(path, root))
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a public Data2Doc2Data Skill ZIP.")
    parser.add_argument("output", type=Path, help="Output .zip path")
    parser.add_argument("--draft", action="store_true", help="Build an unlicensed local draft; do not publish it.")
    args = parser.parse_args(argv)
    output = build_bundle(args.output, draft=args.draft)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
