import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from sqlalchemy import create_engine, inspect, text

from app.main import ensure_chat_message_usage_column
from app.services import chat_usage
from app.services.chat_context import token_count
from app.services.chat_usage import ChatUsageTracker
from server_core.config import _optional_token_price


class ChatUsageTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = ChatUsageTracker()
        self.run_id = uuid4()
        self.prompt_messages = [[
            SystemMessage(content="Answer clearly."),
            HumanMessage(content="What is the policy?"),
        ]]
        self.tracker.on_chat_model_start({}, self.prompt_messages, run_id=self.run_id)

    def test_provider_usage_metadata_is_accumulated_and_costed(self):
        response = LLMResult(
            generations=[[ChatGeneration(message=AIMessage(
                content="A concise answer.",
                usage_metadata={"input_tokens": 120, "output_tokens": 35, "total_tokens": 155},
            ))]],
            llm_output={"token_usage": {"prompt_tokens": 120, "completion_tokens": 35}},
        )
        with patch.object(chat_usage.settings, "llm_input_price_per_1m", 2.0), patch.object(
            chat_usage.settings, "llm_output_price_per_1m", 8.0,
        ):
            self.tracker.on_llm_end(response, run_id=self.run_id)
            self.tracker.on_llm_end(response, run_id=self.run_id)
            usage = self.tracker.snapshot()

        self.assertEqual(usage["input_tokens"], 120)
        self.assertEqual(usage["output_tokens"], 35)
        self.assertEqual(usage["total_tokens"], 155)
        self.assertFalse(usage["tokens_estimated"])
        self.assertEqual(usage["cost_usd"], 0.00052)

    def test_missing_provider_usage_falls_back_to_estimate_and_missing_prices_are_null(self):
        response = LLMResult(
            generations=[[ChatGeneration(message=AIMessage(content="Estimated answer text."))]],
            llm_output={},
        )
        with patch.object(chat_usage.settings, "llm_input_price_per_1m", None), patch.object(
            chat_usage.settings, "llm_output_price_per_1m", None,
        ):
            self.tracker.on_llm_end(response, run_id=self.run_id)
            usage = self.tracker.snapshot()

        expected_prompt = sum(
            token_count(f"{message.type}: {message.content}") + 4
            for message in self.prompt_messages[0]
        )
        self.assertEqual(usage["input_tokens"], expected_prompt)
        self.assertEqual(usage["output_tokens"], token_count("Estimated answer text."))
        self.assertTrue(usage["tokens_estimated"])
        self.assertIsNone(usage["cost_usd"])
        self.assertFalse(usage["pricing_configured"])

    def test_optional_price_accepts_nonnegative_values_and_rejects_invalid_values(self):
        with patch.dict(os.environ, {"TEST_TOKEN_PRICE": "0.25"}):
            self.assertEqual(_optional_token_price("TEST_TOKEN_PRICE"), 0.25)
        with patch.dict(os.environ, {"TEST_TOKEN_PRICE": "-0.1"}):
            with self.assertRaises(ValueError):
                _optional_token_price("TEST_TOKEN_PRICE")
        with patch.dict(os.environ, {"TEST_TOKEN_PRICE": "nan"}):
            with self.assertRaises(ValueError):
                _optional_token_price("TEST_TOKEN_PRICE")


class ChatUsageMigrationTests(unittest.TestCase):
    def test_existing_chat_message_table_gets_usage_column_idempotently(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE chat_messages (id VARCHAR(36) PRIMARY KEY)"))

        ensure_chat_message_usage_column(engine)
        ensure_chat_message_usage_column(engine)

        columns = {column["name"] for column in inspect(engine).get_columns("chat_messages")}
        self.assertIn("usage", columns)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
