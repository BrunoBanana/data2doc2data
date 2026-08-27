from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_changelog_records_the_one_command_github_launcher(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("`ddd web`", changelog)
        self.assertIn(
            "`uvx --from git+https://github.com/BrunoBanana/data2doc2data ddd web`",
            changelog,
        )

    def test_package_metadata_declares_the_mit_license(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('license = "MIT"', pyproject)
        self.assertNotIn('license = { text = "MIT" }', pyproject)

    def test_v31_metadata_agrees_across_release_surfaces_and_records_history(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        lockfile = (ROOT / "uv.lock").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        bundle_builder = (ROOT / "scripts" / "build_skill_bundle.py").read_text(encoding="utf-8")
        mcp_server = (ROOT / "src" / "data2doc2data" / "mcp_server.py").read_text(encoding="utf-8")
        provenance = (ROOT / "src" / "data2doc2data" / "provenance.py").read_text(encoding="utf-8")
        codex = (ROOT / "src" / "data2doc2data" / "agents" / "codex.py").read_text(encoding="utf-8")
        workbuddy = (ROOT / "src" / "data2doc2data" / "agents" / "workbuddy.py").read_text(encoding="utf-8")
        codex_plugin = (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        codebuddy_plugin = (ROOT / ".codebuddy-plugin" / "plugin.json").read_text(encoding="utf-8")

        self.assertIn('version = "3.1.0"', pyproject)
        self.assertIn('name = "data2doc2data"\nversion = "3.1.0"', lockfile)
        self.assertIn('("version", "3.1.0")', bundle_builder)
        self.assertIn('SERVER_VERSION = "3.1.0"', mcp_server)
        self.assertIn('ENGINE_VERSION = "3.1.0"', provenance)
        self.assertIn('"version": "3.1.0"', codex)
        self.assertIn('"version": "3.1.0"', workbuddy)
        self.assertIn('"version": "3.1.0"', codex_plugin)
        self.assertIn('"version": "3.1.0"', codebuddy_plugin)
        self.assertIn("Current version: **v3.1.0**", readme)
        self.assertIn("data2doc2data-v3.1.0.zip", readme)
        self.assertIn("## [3.1.0] - 2026-08-27", changelog)
        self.assertIn("## [3.0.0]", changelog)
        self.assertIn("## [2.9.0]", changelog)
        self.assertIn("## [2.8.0]", changelog)
        self.assertIn("## [2.7.0]", changelog)
        self.assertIn("## [2.6.0]", changelog)
        self.assertIn("## [2.5.0]", changelog)
        self.assertIn("## [2.4.0]", changelog)
        self.assertIn("## [2.3.0]", changelog)
        self.assertIn("## [2.2.0]", changelog)
        self.assertIn("## [2.1.0]", changelog)
        self.assertIn("## [2.0.0]", changelog)
        self.assertIn("## [1.9.0]", changelog)
        self.assertIn("## [1.8.0]", changelog)
        self.assertIn("## [1.7.0]", changelog)
        self.assertIn("## [1.6.0]", changelog)
        self.assertIn("## [1.5.0]", changelog)
        self.assertIn("## [1.4.0]", changelog)
        self.assertIn("## [1.3.0]", changelog)
        self.assertIn("## [1.2.0]", changelog)
        self.assertIn("## [1.1.0]", changelog)
        self.assertIn("## [1.0.0]", changelog)

    def test_package_data_includes_nested_demo_catalog_and_fixtures(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('"sample/scenarios/*.json"', pyproject)
        self.assertIn('"sample/scenarios/*/*.csv"', pyproject)
        self.assertIn('"sample/scenarios/*/*.md"', pyproject)
        self.assertIn('"static/dist/assets/*"', pyproject)

    def test_source_distribution_excludes_non_runtime_private_boundaries(self):
        manifest_path = ROOT / "MANIFEST.in"

        self.assertTrue(manifest_path.is_file())
        manifest = manifest_path.read_text(encoding="utf-8")
        self.assertIn("prune tests", manifest)
        self.assertIn("prune docs/pitch", manifest)


if __name__ == "__main__":
    unittest.main()
