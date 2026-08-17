from pathlib import Path
import unittest


STATIC_ROOT = Path(__file__).resolve().parents[1] / "src" / "data2doc2data" / "static"


class StaticAssetTests(unittest.TestCase):
    def test_page_uses_only_local_assets_and_has_required_controls(self):
        html = read_static("index.html")

        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)
        for control in ("data-mode", "data-path", "knowledge-path", "agent-message", "conversation-log"):
            self.assertIn(f'id="{control}"', html)

    def test_page_uses_chinese_product_copy(self):
        html = read_static("index.html")
        script = read_all_js()

        self.assertIn('<html lang="zh-CN">', html)
        for copy in ("本地证据工作台", "先理解指标，再采取行动。", "证据流程", "数据源设置"):
            self.assertIn(copy, html)
        for copy in ("确定性结论", "验证：", "正在保存数据源"):
            self.assertIn(copy, script)
        self.assertNotIn("Local evidence workspace", html)

    def test_styles_include_focus_and_reduced_motion_support(self):
        css = read_static("app.css")

        self.assertIn("[hidden]", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("transform: scale(.97)", css)

    def test_deterministic_message_and_pipeline_state_have_semantic_style(self):
        script = read_all_js()
        css = read_static("app.css")
        html = read_static("index.html")

        self.assertIn('data-step="verification"', html)
        self.assertIn('"deterministic"', script)
        self.assertIn(".message-deterministic", css)
        self.assertIn('[data-state="done"]', css)
        self.assertIn('[data-state="error"]', css)

    def test_pipeline_exposes_verification_step(self):
        html = read_static("index.html")
        script = read_all_js()

        self.assertIn('data-step="verification"', html)
        self.assertIn('data-step="conclusion"', html)
        self.assertIn("analysis.verification", script)
        self.assertIn("analysis.validation", script)

    def test_script_calls_only_loopback_api_routes(self):
        script = read_all_js()

        for route in (
            "/api/profile",
            "/api/demo-scenarios",
            "/api/analyze",
            "/api/agents",
            "/api/agent-sessions",
        ):
            self.assertIn(route, script)
        self.assertNotIn("https://", script)
        self.assertNotIn("http://", script)


def read_static(name: str) -> str:
    path = STATIC_ROOT / name
    if not path.is_file():
        raise AssertionError(f"missing static asset: {name}")
    return path.read_text(encoding="utf-8")


def read_all_js() -> str:
    """Concatenate every local script module so security and feature contracts
    cover the whole frontend, not just the entry file."""
    parts = []
    for path in sorted(STATIC_ROOT.glob("*.js")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


if __name__ == "__main__":
    unittest.main()
