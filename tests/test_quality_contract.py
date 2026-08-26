from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class QualityContractTests(unittest.TestCase):
    ONE_COMMAND_LAUNCH = (
        "uvx --from git+https://github.com/BrunoBanana/data2doc2data ddd web"
    )

    def test_ci_runs_the_complete_unittest_suite(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn('python-version: ["3.10", "3.11", "3.12", "3.13"]', workflow)

    def test_development_tools_are_optional_dependencies(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("[project.optional-dependencies]", pyproject)
        self.assertIn('coverage[toml]>=7.6', pyproject)
        self.assertIn('ruff>=0.9', pyproject)

    def test_python_310_has_a_runtime_tomllib_backport(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("tomli>=2; python_version < '3.11'", pyproject)

    def test_package_exposes_long_and_short_cli_entry_points(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('data2doc2data = "data2doc2data.cli:main"', pyproject)
        self.assertIn('ddd = "data2doc2data.cli:main"', pyproject)

    def test_readme_leads_with_bilingual_one_command_launch(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertGreaterEqual(readme.count(self.ONE_COMMAND_LAUNCH), 2)
        self.assertIn("## Quick start", readme)
        self.assertIn("## 快速开始", readme)
        self.assertIn("## Developer installation", readme)
        self.assertIn("## 开发者安装", readme)
        self.assertLess(readme.index("## Quick start"), readme.index("## Developer installation"))
        self.assertLess(readme.index("## 快速开始"), readme.index("## 开发者安装"))
        self.assertIn("https://docs.astral.sh/uv/getting-started/installation/", readme)
        self.assertIn("127.0.0.1:8781", readme)
        self.assertIn("--no-open", readme)
        self.assertIn("No model, API key, data file, or document is required for Demo mode.", readme)
        self.assertIn("Demo 模式不需要模型、API Key、数据文件或文档", readme)

    def test_coverage_measures_production_code_only(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("[tool.coverage.run]", pyproject)
        self.assertIn('source = ["src/data2doc2data", "scripts"]', pyproject)


if __name__ == "__main__":
    unittest.main()
