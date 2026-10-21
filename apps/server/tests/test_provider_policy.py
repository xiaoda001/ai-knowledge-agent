import unittest
from unittest.mock import patch

from app.agents.providers import llm as llm_provider
from app.agents.providers.redaction import redact


class CloudLlmConfigurationTests(unittest.TestCase):
    def test_remote_provider_needs_https_but_not_approval_or_host_allowlist(self):
        settings = llm_provider.settings
        with patch.object(settings, "llm_mode", True), patch.object(
            settings, "llm_base_url", "https://api.example.test/v1",
        ), patch.object(settings, "llm_model", "chat-model"), patch.object(
            settings, "llm_api_key", "",
        ), patch.object(
            llm_provider, "ChatOpenAI",
        ) as client:
            result = llm_provider.llm_for_request()

        self.assertIs(result, client.return_value)
        client.assert_called_once_with(base_url="https://api.example.test/v1", api_key="local",
                                       model="chat-model", streaming=True, stream_usage=False,
                                       callbacks=[],
                                       extra_body={"enable_thinking": False})

    def test_remote_http_provider_is_rejected(self):
        settings = llm_provider.settings
        with patch.object(settings, "llm_mode", True), patch.object(
            settings, "llm_base_url", "http://api.example.test/v1",
        ), patch.object(settings, "llm_model", "chat-model"), patch.object(
            settings, "llm_api_key", "",
        ), patch.object(llm_provider, "ChatOpenAI") as client:
            with self.assertRaisesRegex(RuntimeError, "HTTPS"):
                llm_provider.llm_for_request()

        client.assert_not_called()


class OptionalRedactionTests(unittest.TestCase):
    def test_unconfigured_redaction_rules_leave_text_unchanged(self):
        settings = llm_provider.settings
        with patch("app.agents.providers.redaction.settings.llm_mode", True), patch(
            "app.agents.providers.redaction.settings.llm_base_url", "https://api.example.test/v1",
        ), patch("app.agents.providers.redaction.settings.redaction_rules", ""):
            self.assertEqual(redact("原始问题"), "原始问题")

    def test_configured_redaction_rules_are_applied(self):
        with patch("app.agents.providers.redaction.settings.llm_mode", True), patch(
            "app.agents.providers.redaction.settings.llm_base_url", "https://api.example.test/v1",
        ), patch("app.agents.providers.redaction.settings.redaction_rules",
                 '[{"pattern":"secret", "replacement":"[MASKED]"}]'):
            self.assertEqual(redact("secret value"), "[MASKED] value")

    def test_invalid_configured_redaction_fails_closed(self):
        with patch("app.agents.providers.redaction.settings.llm_mode", True), patch(
            "app.agents.providers.redaction.settings.llm_base_url", "https://api.example.test/v1",
        ), patch("app.agents.providers.redaction.settings.redaction_rules", "not-json"):
            with self.assertRaisesRegex(RuntimeError, "Redaction policy failed"):
                redact("secret")


if __name__ == "__main__":
    unittest.main()
