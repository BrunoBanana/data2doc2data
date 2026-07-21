"""Regression guard for material that must never enter the public package."""

from __future__ import annotations

from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SUFFIXES = {".css", ".csv", ".html", ".js", ".md", ".py", ".toml", ".yaml"}
FORBIDDEN_PRIVATE_MARKERS = (
    "private-data-platform",
    "internal-domain",
    "internal-org",
    "internal-agent-platform",
)


class PublicBoundaryTests(unittest.TestCase):
    def test_public_package_contains_no_private_markers(self) -> None:
        files = [
            path
            for path in PACKAGE_ROOT.rglob("*")
            if path.is_file()
            and "tests" not in path.relative_to(PACKAGE_ROOT).parts
            and path.suffix in PUBLIC_SUFFIXES
        ]

        self.assertTrue(files, "Expected public package files to audit")
        matches: list[str] = []
        for path in files:
            content = path.read_text(encoding="utf-8").lower()
            for marker in FORBIDDEN_PRIVATE_MARKERS:
                if marker in content:
                    matches.append(f"{path.relative_to(PACKAGE_ROOT)}: {marker}")

        self.assertEqual(matches, [], "Private markers found in public package")

