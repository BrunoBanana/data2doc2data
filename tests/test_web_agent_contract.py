from pathlib import Path
import unittest


STATIC_ROOT = Path(__file__).resolve().parents[1] / "src" / "data2doc2data" / "static"


class WebAgentContractTests(unittest.TestCase):
    def test_page_exposes_accessible_agent_controls(self):
        html = read_static("index.html")

        for control in (
            "agent-provider",
            "permission-mode",
            "agent-connect",
            "agent-interrupt",
            "conversation-log",
            "agent-message-form",
            "agent-message",
            "agent-send",
            "operation-queue",
            "agent-status",
        ):
            self.assertIn(f'id="{control}"', html)
        self.assertIn('role="log"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn("本地助手", html)

    def test_script_uses_csrf_session_api_and_event_source(self):
        script = read_all_js()

        for route in (
            '"/api/agents"',
            '"/api/agent-sessions"',
            '}/messages`',
            '}/events`',
            '}/approvals/${encodeURIComponent(approvalId)}`',
            '}/interrupt`',
        ):
            self.assertIn(route, script)
        self.assertIn('"X-CSRF-Token"', script)
        self.assertIn("new EventSource", script)
        self.assertIn("eventSource.close()", script)

    def test_provider_content_is_rendered_as_text_not_markup(self):
        script = read_all_js()

        self.assertIn("textContent", script)
        self.assertIn("document.createElement", script)
        self.assertIn('approveButton.textContent = "批准"', script)
        self.assertIn('rejectButton.textContent = "拒绝"', script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)
        self.assertNotIn("eval(", script)

    def test_agent_layout_has_responsive_and_operation_styles(self):
        css = read_static("app.css")

        for selector in (
            ".assistant-toolbar",
            ".conversation-log",
            ".message-card",
            ".approval-card",
            ".operation-queue",
        ):
            self.assertIn(selector, css)
        self.assertIn("@media (max-width: 880px)", css)

    def test_deterministic_message_is_marked_as_authoritative(self):
        script = read_all_js()
        css = read_static("app.css")

        self.assertIn('"deterministic"', script)
        self.assertIn(".message-deterministic", css)
        self.assertIn('"确定性"', script)


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
