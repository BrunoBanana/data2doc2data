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
        script = read_static("app.js")

        self.assertIn('request("/api/demo-scenarios")', script)
        self.assertIn("document.createElement(\"option\")", script)
        self.assertIn("option.textContent = scenario.label", script)
        self.assertIn("demo_scenario: demoScenario.value", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)

    def test_demo_metadata_updates_suggested_question_only_on_explicit_change(self):
        script = read_static("app.js")

        self.assertIn('demoScenario.addEventListener("change"', script)
        self.assertIn("analysisQuestion.value = scenario.suggested_question", script)
        change_handler = script.split('demoScenario.addEventListener("change"', 1)[1]
        change_handler = change_handler.split("});", 1)[0]
        self.assertNotIn("requestSubmit", change_handler)
        self.assertNotIn("/api/analyze", change_handler)

    def test_mode_switch_hides_demo_selector_without_clearing_local_or_results_state(self):
        script = read_static("app.js")

        self.assertIn("demoScenarioFields.hidden = isLocal", script)
        self.assertIn("localFields.hidden = !isLocal", script)
        sync_body = script.split("function syncSourceMode()", 1)[1].split("}", 1)[0]
        self.assertNotIn("dataPath.value =", sync_body)
        self.assertNotIn("knowledgePath.value =", sync_body)
        self.assertNotIn("analysisResult", sync_body)

    def test_contradicted_result_has_a_semantic_label_and_style(self):
        script = read_static("app.js")
        css = read_static("app.css")

        self.assertIn('contradicted: "与策略矛盾"', script)
        self.assertIn('[data-status="contradicted"]', css)

    def test_grid_children_can_shrink_at_the_mobile_breakpoint(self):
        css = read_static("app.css")

        self.assertIn(".workspace { display: grid; gap: 20px; min-width: 0; }", css)
        self.assertIn(".context-panel {", css)
        self.assertIn("min-width: 0;", css)


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
