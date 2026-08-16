from pathlib import Path
import unittest


STATIC_ROOT = Path(__file__).resolve().parents[1] / "src" / "data2doc2data" / "static"


class StaticAssetTests(unittest.TestCase):
    def test_setup_page_uses_only_local_assets_and_has_required_controls(self):
        html = read_static("index.html")

        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)
        for control in ("data-mode", "data-path", "knowledge-path", "analysis-question", "metric-override"):
            self.assertIn(f'id="{control}"', html)

    def test_setup_page_uses_chinese_product_copy(self):
        html = read_static("index.html")
        script = read_static("app.js")

        self.assertIn('<html lang="zh-CN">', html)
        for copy in ("本地证据工作台", "先理解指标，再采取行动。", "选择要分析的内容", "开始分析"):
            self.assertIn(copy, html)
        for copy in ("正在读取本地证据", "分析完成。", "留存率", "获得数据支持"):
            self.assertIn(copy, script)
        self.assertNotIn("Local evidence workspace", html)

    def test_styles_include_focus_and_reduced_motion_support(self):
        css = read_static("app.css")

        self.assertIn("[hidden]", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("transform: scale(.97)", css)

    def test_validation_status_has_semantic_style_contract(self):
        script = read_static("app.js")
        css = read_static("app.css")

        self.assertIn("dataset.status = result.validation.status", script)
        self.assertIn('[data-status="mixed"]', css)
        self.assertIn('[data-status="insufficient"]', css)

    def test_setup_page_renders_secondary_data_verification(self):
        html = read_static("index.html")
        script = read_static("app.js")

        self.assertIn('id="result-verification-title"', html)
        self.assertIn('id="result-verification-copy"', html)
        self.assertIn("result.verification", script)

    def test_script_calls_only_loopback_api_routes(self):
        script = read_static("app.js")

        for route in ("/api/profile", "/api/analyze", "/api/agents", "/api/agent-sessions"):
            self.assertIn(route, script)
        self.assertIn("metric_override", script)
        self.assertNotIn("https://", script)
        self.assertNotIn("http://", script)


def read_static(name: str) -> str:
    path = STATIC_ROOT / name
    if not path.is_file():
        raise AssertionError(f"missing static asset: {name}")
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
