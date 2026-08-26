from pathlib import Path
import unittest


STATIC_ROOT = Path(__file__).resolve().parents[1] / "src" / "data2doc2data" / "static"


class WebDemoContractTests(unittest.TestCase):
    def test_demo_selector_has_accessible_description_and_live_metadata(self):
        html = read_static("index.html")

        self.assertIn('id="demo-scenario-fields"', html)
        self.assertIn('for="demo-scenario"', html)
        self.assertIn('id="demo-scenario"', html)
        self.assertIn('aria-describedby="demo-scenario-summary demo-scenario-objective"', html)
        self.assertIn('id="demo-scenario-summary"', html)
        self.assertIn('id="demo-scenario-objective"', html)
        self.assertGreaterEqual(html.count('aria-live="polite"'), 2)

    def test_scenarios_are_loaded_rendered_and_persisted_without_html_injection(self):
        script = read_all_js()

        self.assertIn('request("/api/demo-scenarios")', script)
        self.assertIn("document.createElement(\"option\")", script)
        self.assertIn("option.textContent = scenario.label", script)
        self.assertIn("demo_scenario: demoScenario.value", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)

    def test_demo_selector_change_does_not_trigger_analysis(self):
        script = read_all_js()

        self.assertIn('demoScenario.addEventListener("change"', script)
        change_handler = script.split('demoScenario.addEventListener("change"', 1)[1]
        change_handler = change_handler.split("});", 1)[0]
        self.assertNotIn("/api/analyze", change_handler)

    def test_mode_switch_hides_demo_selector_without_clearing_local_state(self):
        script = read_all_js()

        self.assertIn("demoScenarioFields.hidden = isLocal", script)
        self.assertIn("localFields.hidden = !isLocal", script)
        sync_body = script.split("function syncSourceMode()", 1)[1].split("}", 1)[0]
        self.assertNotIn("dataPath.value =", sync_body)
        self.assertNotIn("knowledgePath.value =", sync_body)

    def test_validation_status_has_a_semantic_label(self):
        script = read_all_js()

        self.assertIn('contradicted: "与策略矛盾"', script)
        self.assertIn("VALIDATION_STATUS_LABELS", script)

    def test_pipeline_and_log_children_can_shrink(self):
        css = read_static("app.css")

        self.assertIn("min-width: 0;", css)
        self.assertIn(".pipeline-pane {", css)
        self.assertIn(".conversation-log {", css)


def read_static(name: str) -> str:
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
