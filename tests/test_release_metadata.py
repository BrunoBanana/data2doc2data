from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_package_metadata_declares_the_mit_license(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('license = { text = "MIT" }', pyproject)

    def test_v2_9_metadata_records_release_history(self):
        self.assertIn('version = "2.9.0"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
