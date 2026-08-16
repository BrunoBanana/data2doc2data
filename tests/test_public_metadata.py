from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TITLE = "Data2Doc2Data-面向真实业务的数据+文本循环推理架构"


class PublicMetadataTests(unittest.TestCase):
    def test_skill_has_trigger_frontmatter_and_no_internal_terms(self):
        skill_path = ROOT / "SKILL.md"
        self.assertTrue(skill_path.is_file())
        text = skill_path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: data2doc2data\n"))
        self.assertIn("description:", text.split("---", 2)[1])

        for term in ("private-data-platform", "internal-org", "internal-agent-platform", "internal-domain"):
            self.assertNotIn(term, text.lower())

    def test_source_skill_uses_only_standard_trigger_frontmatter(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]

        for field in ("slug", "version", "displayName", "summary", "tags", "license"):
            self.assertNotIn(f"\n{field}:", frontmatter)

    def test_public_title_and_descriptions_use_chinese(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        agent_metadata = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertIn("description: 面向真实业务场景", skill)
        self.assertIn(f'display_name: "{PUBLIC_TITLE}"', agent_metadata)
        self.assertIn("short_description: \"让数据与文本形成可验证、可追溯、可行动的真实业务循环推理闭环。\"", agent_metadata)
        self.assertIn("default_prompt: \"使用 $data2doc2data", agent_metadata)

    def test_user_facing_markdown_uses_chinese_titles(self):
        expected_titles = {
            "README.md": f"# {PUBLIC_TITLE}",
            "SKILL.md": f"# {PUBLIC_TITLE}",
            "CHANGELOG.md": "# 更新日志",
            "references/connector-guide.md": "# 数据连接器指南",
        }

        for relative_path, title in expected_titles.items():
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn(title, text, relative_path)

    def test_public_samples_use_generic_business_context(self):
        scenario_dir = ROOT / "src" / "data2doc2data" / "sample" / "scenarios"
        self.assertTrue((scenario_dir / "catalog.json").is_file())
        for scenario in (
            "growth-quality-alert",
            "strategy-data-conflict",
            "insufficient-evidence",
        ):
            self.assertTrue((scenario_dir / scenario / "metrics.csv").is_file())
            document = (scenario_dir / scenario / "strategy.md").read_text(encoding="utf-8")
            self.assertIn("虚构合成数据", document)

    def test_operator_docs_cover_local_agents_permissions_and_demo_boundaries(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        connector_guide = (ROOT / "references" / "connector-guide.md").read_text(encoding="utf-8")

        for term in (
            "Codex",
            "腾讯 WorkBuddy",
            "codebuddy",
            "只读模式",
            "协作模式",
            "信任本次会话",
            "冷启动",
            "确定性分析",
            "虚构合成数据",
        ):
            self.assertIn(term, readme)
        self.assertIn("三套", skill)
        self.assertIn("本地智能助手不是数据连接器", connector_guide)

    def test_operator_docs_explain_grounded_context_and_local_compute_boundary(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        for term in (
            "三栏工作台",
            "原始 CSV 始终留在本机",
            "统计摘要",
            "相关文档片段",
            "自动压缩",
            "证据快照",
        ):
            self.assertIn(term, readme)
        self.assertIn("证据上下文", changelog)
        self.assertNotIn("网页不会静默附加 CSV 或文档内容", readme)

    def test_public_release_text_has_no_stale_v0_1_label(self):
        for relative_path in (
            "README.md",
            "SKILL.md",
            "references/connector-guide.md",
            "src/data2doc2data/analysis.py",
        ):
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("v0.1", text, relative_path)


if __name__ == "__main__":
    unittest.main()
