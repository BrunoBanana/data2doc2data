from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class QualityContractTests(unittest.TestCase):
    def test_ci_runs_the_complete_unittest_suite(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn('python-version: ["3.10", "3.11", "3.12", "3.13"]', workflow)

    def test_development_tools_are_optional_dependencies(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("[project.optional-dependencies]", pyproject)
        self.assertIn('coverage>=7.6', pyproject)
        self.assertIn('ruff>=0.9', pyproject)

    def test_coverage_measures_production_code_only(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("[tool.coverage.run]", pyproject)
        self.assertIn('source = ["src/data2doc2data", "scripts"]', pyproject)


if __name__ == "__main__":
    unittest.main()
