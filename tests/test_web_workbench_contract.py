from pathlib import Path
import unittest


STATIC_ROOT = Path(__file__).resolve().parents[1] / "src" / "data2doc2data" / "static"


class WebWorkbenchContractTests(unittest.TestCase):
    def test_page_has_two_coordinated_panes_and_status_bar(self):
        html = read_static("index.html")

        for identifier in (
            "workbench-shell",
            "active-source-status",
            "privacy-status",
        ):
            self.assertIn(f'id="{identifier}"', html)
        for class_name in ("conversation-pane", "pipeline-pane", "pipeline-steps"):
            self.assertIn(class_name, html)

    def test_page_exposes_dataset_profile_and_pipeline_metadata(self):
        html = read_static("index.html")

        for identifier in (
            "source-record-count",
            "source-metric-count",
            "source-document-count",
            "agent-context-status",
            "context-snapshot-id",
            "context-contract-version",
            "pipeline-steps",
        ):
            self.assertIn(f'id="{identifier}"', html)
        self.assertIn("证据流程", html)

    def test_pipeline_exposes_five_ordered_steps(self):
        html = read_static("index.html")

        steps = ("source", "signal", "retrieval", "verification", "conclusion")
        positions = [html.index(f'data-step="{step}"') for step in steps]
        self.assertEqual(positions, sorted(positions))

    def test_script_renders_pipeline_and_context_events_safely(self):
        script = read_all_js()

        self.assertIn('request("/api/source-profile")', script)
        self.assertIn('case "context.attached"', script)
        self.assertIn("renderPipeline", script)
        self.assertIn("renderContextSummary", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)

    def test_compact_workbench_uses_readable_type_and_targets(self):
        css = read_static("app.css")

        self.assertIn("--font-caption: 12px", css)
        self.assertIn("--control-compact: 38px", css)
        self.assertIn("min-height: var(--control-compact)", css)
        self.assertIn("flex-wrap: wrap", css)
        self.assertIn(".message-copy blockquote", css)
        self.assertIn(".message-copy h2", css)
        self.assertNotIn("font-size: 9px", css)


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
