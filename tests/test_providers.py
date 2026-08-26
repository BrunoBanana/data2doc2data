import unittest

from data2doc2data.agents.base import ProviderStatus
from data2doc2data.agents.gateway import AgentGateway
from data2doc2data.providers import ProviderRegistry, ProviderRegistryError


class FakeProvider:
    def __init__(self, name, status):
        self.name = name
        self.status = status

    def detect(self):
        return self.status

    def close(self):
        return None


class ProviderRegistryTests(unittest.TestCase):
    def test_local_cli_statuses_have_capabilities_and_reconnect_hints(self):
        gateway = AgentGateway(
            {
                "codex": FakeProvider("codex", ProviderStatus(True, False, version="1.2", authenticated=True)),
                "workbuddy": FakeProvider(
                    "workbuddy",
                    ProviderStatus(True, False, version="2.115", authenticated=False, detail="authorization expired"),
                ),
            }
        )

        connections = ProviderRegistry(gateway).list_connections()

        codex = next(item for item in connections if item["provider_id"] == "codex")
        workbuddy = next(item for item in connections if item["provider_id"] == "workbuddy")
        self.assertEqual(codex["state"], "ready")
        self.assertIn("streaming", codex["capabilities"])
        self.assertEqual(workbuddy["state"], "auth_required")
        self.assertIn("重新登录", workbuddy["reconnect_hint"])

    def test_api_connection_uses_only_env_or_keychain_secret_references(self):
        registry = ProviderRegistry(AgentGateway({}), environ={"D2D2D_API_KEY": "private-value"})

        configured = registry.configure_openai_compatible(
            {
                "provider_id": "company-api",
                "base_url": "https://llm.example.com/v1",
                "model": "company-model",
                "secret_ref": "env:D2D2D_API_KEY",
            }
        )

        self.assertEqual(configured["state"], "ready")
        self.assertEqual(configured["config"]["secret_ref"], "env:D2D2D_API_KEY")
        self.assertNotIn("private-value", str(configured))
        with self.assertRaisesRegex(ProviderRegistryError, "secret"):
            registry.configure_openai_compatible(
                {
                    "provider_id": "bad-api",
                    "base_url": "https://llm.example.com/v1",
                    "model": "model",
                    "secret_ref": "sk-raw-secret",
                }
            )

    def test_skip_mode_is_explicit_and_missing_env_is_auth_required(self):
        registry = ProviderRegistry(AgentGateway({}), environ={})
        missing = registry.configure_openai_compatible(
            {
                "provider_id": "company-api",
                "base_url": "https://llm.example.com/v1",
                "model": "company-model",
                "secret_ref": "env:MISSING_KEY",
            }
        )

        self.assertEqual(missing["state"], "auth_required")
        self.assertEqual(registry.skip()["state"], "skipped")


if __name__ == "__main__":
    unittest.main()
