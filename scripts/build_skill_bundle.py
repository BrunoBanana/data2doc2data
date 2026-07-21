"""Build a deterministic ZIP suitable for a SkillHub-style upload."""

from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("README.md", "SKILL.md", "pyproject.toml")
RESOURCE_DIRECTORIES = ("agents", "references", "src/data2doc2data")
EXCLUDED_PARTS = {"__pycache__"}
PUBLIC_RESOURCE_SUFFIXES = {".css", ".csv", ".html", ".js", ".md", ".py", ".svg", ".txt", ".yaml"}
SKILLHUB_METADATA = (
    ("slug", "data2doc2data"),
    ("version", "2.9.0"),
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


def bundle_files(root: Path = ROOT) -> list[Path]:
    """Return the public Skill files in a stable order."""
    files = [root / name for name in ROOT_FILES]
    if (root / "LICENSE").is_file():
        files.append(root / "LICENSE")
    for directory in RESOURCE_DIRECTORIES:
        files.extend(
            path
            for path in (root / directory).rglob("*")
            if _is_public_resource(path, root)
        )
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _is_public_resource(path: Path, root: Path) -> bool:
    relative_path = path.relative_to(root)
    return (
        path.is_file()
        and not path.is_symlink()
        and path.suffix.lower() in PUBLIC_RESOURCE_SUFFIXES
        and not EXCLUDED_PARTS.intersection(relative_path.parts)
        and not any(part.startswith(".") for part in relative_path.parts)
    )


def _validate_public_contents(files: list[Path], root: Path) -> None:
    for path in files:
        content = path.read_text(encoding="utf-8").lower()
        for marker in FORBIDDEN_PRIVATE_MARKERS:
            if marker in content:
                relative_path = path.relative_to(root).as_posix()
                raise ValueError(f"public bundle contains a private marker in {relative_path}")


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
