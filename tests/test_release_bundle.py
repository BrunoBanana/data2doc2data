from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bundle_builder", ROOT / "scripts" / "build_skill_bundle.py")
assert SPEC and SPEC.loader
BUNDLE_BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUNDLE_BUILDER)


class ReleaseBundleTests(unittest.TestCase):
    def test_public_bundle_requires_a_license(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            root.mkdir()
            for name in ("README.md", "SKILL.md", "pyproject.toml"):
                (root / name).write_text(name, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "LICENSE is required"):
                BUNDLE_BUILDER.build_bundle(Path(directory) / "bundle.zip", root=root)

    def test_skillhub_bundle_contains_runtime_and_skill_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data2doc2data.zip"
            completed = subprocess.run(
                [sys.executable, "scripts/build_skill_bundle.py", str(output), "--draft"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                skill_contract = archive.read("SKILL.md").decode("utf-8")

            self.assertTrue(
                {
                    "SKILL.md",
                    "agents/openai.yaml",
                    "references/connector-guide.md",
                    "pyproject.toml",
                    "src/data2doc2data/cli.py",
                    "src/data2doc2data/static/index.html",
                }.issubset(names)
            )
            self.assertFalse(any(".egg-info/" in name or "__pycache__/" in name for name in names))

            for field in (
                "slug: data2doc2data",
                "version: 2.9.0",
                "displayName: Data2Doc2Data-面向真实业务的数据+文本循环推理架构",
                "summary: 面向真实业务场景，让数据指标与策略、决策文档形成可验证的循环推理。",
                "tags: [analytics, local-first, evidence]",
                "license: MIT",
            ):
                self.assertIn(field, skill_contract)

    def test_public_bundle_contains_the_selected_mit_license(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data2doc2data.zip"
            completed = subprocess.run(
                [sys.executable, "scripts/build_skill_bundle.py", str(output)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            with zipfile.ZipFile(output) as archive:
                self.assertIn("LICENSE.md", archive.namelist())
                self.assertTrue(archive.read("LICENSE.md").decode("utf-8").startswith("MIT License\n"))

    def test_bundle_omits_hidden_or_unapproved_resource_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            (root / "agents").mkdir(parents=True)
            (root / "references").mkdir()
            runtime = root / "src" / "data2doc2data"
            runtime.mkdir(parents=True)
            for name in ("README.md", "pyproject.toml", "LICENSE"):
                (root / name).write_text(name, encoding="utf-8")
            (root / "SKILL.md").write_text(
                "---\nname: test-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            (root / "agents" / "openai.yaml").write_text("name: test\n", encoding="utf-8")
            (root / "references" / "guide.md").write_text("guide", encoding="utf-8")
            (runtime / "analysis.py").write_text("pass\n", encoding="utf-8")
            (runtime / ".env").write_text("API_KEY=do-not-package\n", encoding="utf-8")
            (runtime / "notes.secret").write_text("do-not-package\n", encoding="utf-8")
            output = Path(directory) / "bundle.zip"

            BUNDLE_BUILDER.build_bundle(output, root=root)

            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertIn("src/data2doc2data/analysis.py", names)
            self.assertNotIn("src/data2doc2data/.env", names)
            self.assertNotIn("src/data2doc2data/notes.secret", names)

    def test_bundle_rejects_private_markers_in_public_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            (root / "agents").mkdir(parents=True)
            (root / "references").mkdir()
            runtime = root / "src" / "data2doc2data"
            runtime.mkdir(parents=True)
            for name in ("README.md", "pyproject.toml", "LICENSE"):
                (root / name).write_text(name, encoding="utf-8")
            (root / "SKILL.md").write_text(
                "---\nname: test-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            (root / "agents" / "openai.yaml").write_text("name: test\n", encoding="utf-8")
            (root / "references" / "guide.md").write_text("guide", encoding="utf-8")
            (runtime / "analysis.py").write_text("source = 'private-data-platform'\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "private marker"):
                BUNDLE_BUILDER.build_bundle(Path(directory) / "bundle.zip", root=root)

    def test_bundle_rejects_email_addresses_in_public_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            (root / "src" / "data2doc2data").mkdir(parents=True)
            for name in ("README.md", "pyproject.toml", "LICENSE"):
                (root / name).write_text(name, encoding="utf-8")
            (root / "SKILL.md").write_text(
                "---\nname: test-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            email_address = "employee" + "@" + "private.example"
            (root / "src" / "data2doc2data" / "analysis.py").write_text(
                f'support = "{email_address}"\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "sensitive data"):
                BUNDLE_BUILDER.build_bundle(Path(directory) / "bundle.zip", root=root)

    def test_bundle_omits_unlisted_csv_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill"
            runtime = root / "src" / "data2doc2data"
            runtime.mkdir(parents=True)
            for name in ("README.md", "pyproject.toml", "LICENSE"):
                (root / name).write_text(name, encoding="utf-8")
            (root / "SKILL.md").write_text(
                "---\nname: test-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            (runtime / "analysis.py").write_text("pass\n", encoding="utf-8")
            (runtime / "customer_export.csv").write_text(
                "date,metric,value\n2026-01-01,revenue,999\n",
                encoding="utf-8",
            )
            output = Path(directory) / "bundle.zip"

            BUNDLE_BUILDER.build_bundle(output, root=root)

            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertNotIn("src/data2doc2data/customer_export.csv", names)


if __name__ == "__main__":
    unittest.main()
