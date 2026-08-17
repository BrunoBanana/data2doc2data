from pathlib import Path
import unittest


STATIC_ROOT = Path(__file__).resolve().parents[1] / "src" / "data2doc2data" / "static"


class WebWorkbenchContractTests(unittest.TestCase):
    def test_page_has_three_coordinated_workspace_columns_and_status_bar(self):
        html = read_static("index.html")

        for identifier in (
            "workbench-shell",
            "data-workspace",
            "analysis-workspace",
            "assistant-workspace",
            "active-source-status",
            "privacy-status",
        ):
            self.assertIn(f'id="{identifier}"', html)
        for class_name in ("data-rail", "analysis-canvas", "assistant-rail"):
            self.assertIn(class_name, html)

    def test_page_exposes_dataset_profile_and_attached_context_metadata(self):
        html = read_static("index.html")

        for identifier in (
            "source-record-count",
            "source-metric-count",
            "source-date-range",
            "source-document-count",
            "agent-context-status",
            "context-snapshot-id",
            "context-record-count",
            "context-excerpt-count",
            "context-compression-state",
        ):
            self.assertIn(f'id="{identifier}"', html)
        self.assertIn("本轮证据上下文", html)

    def test_mobile_workspace_tabs_are_accessible_and_stateful(self):
        html = read_static("index.html")
        script = read_all_js()
        css = read_static("app.css")

        self.assertIn('role="tablist"', html)
        self.assertEqual(html.count('role="tab"'), 3)
        self.assertIn('aria-selected="true"', html)
        self.assertIn("setupWorkspaceTabs", script)
        self.assertIn("aria-selected", script)
        self.assertIn("ArrowRight", script)
        self.assertIn("@media (max-width: 980px)", css)

    def test_script_loads_source_profile_and_renders_context_events_safely(self):
        script = read_all_js()

        self.assertIn('request("/api/source-profile")', script)
        self.assertIn('case "context.attached"', script)
        self.assertIn("renderSourceProfile", script)
        self.assertIn("renderContextSummary", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)


def read_static(name):
    return (STATIC_ROOT / name).read_text(encoding="utf-8")




def read_all_js() -> str:
    """Concatenate every local script module so security and feature contracts
    cover the whole frontend, not just the entry file."""
    parts = []
    for path in sorted(STATIC_ROOT.glob("*.js")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


if __name__ == "__main__":
    unittest.main()
