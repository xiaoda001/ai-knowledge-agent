import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.agents.knowledge_qa.intent import StandaloneQuestion, rewrite_followup_question
from app.services import chat_context


class ChatContextTests(unittest.TestCase):
    @staticmethod
    def messages(*contents):
        return [SimpleNamespace(id=f"m{index}", role="user" if index % 2 == 0 else "assistant",
                                content=content)
                for index, content in enumerate(contents)]

    def test_over_budget_prefix_is_summarized_and_recent_complete_turn_is_kept(self):
        messages = self.messages("a" * 10, "b" * 10, "c" * 10, "d" * 10,
                                 "e" * 10, "f" * 10)
        llm = Mock()
        llm.bind.return_value.invoke.return_value = SimpleNamespace(content="Earlier topic: expenses.")
        with patch.object(chat_context, "message_token_count", side_effect=lambda item: len(item.content)):
            prepared = chat_context.prepare_context(messages, "", None, lambda: llm, history_budget=25)

        self.assertTrue(prepared.summary_updated)
        self.assertEqual(prepared.summary_through_message_id, "m3")
        self.assertEqual([item.id for item in prepared.recent_messages], ["m4", "m5"])
        self.assertIn("expenses", prepared.summary)
        llm.bind.return_value.invoke.assert_called_once()

    def test_failed_compaction_keeps_existing_summary_and_does_not_update_marker(self):
        messages = self.messages("a" * 10, "b" * 10, "c" * 10, "d" * 10)
        with patch.object(chat_context, "message_token_count", side_effect=lambda item: len(item.content)):
            prepared = chat_context.prepare_context(
                messages, "existing summary", "prior-marker",
                lambda: (_ for _ in ()).throw(RuntimeError("offline")), history_budget=25,
            )

        self.assertEqual(prepared.summary, "existing summary")
        self.assertFalse(prepared.summary_updated)
        self.assertIsNone(prepared.summary_through_message_id)
        self.assertEqual([item.id for item in prepared.recent_messages], ["m2", "m3"])

    def test_followup_rewrite_only_uses_context_to_make_query_standalone(self):
        llm = Mock()
        structured = llm.with_structured_output.return_value
        structured.invoke.return_value = StandaloneQuestion(question="报销制度的提交期限是什么？")

        question = rewrite_followup_question(
            llm, "那期限呢？", [("user", "报销制度是什么？"), ("assistant", "说明如下")],
            "当前主题是报销制度。",
        )

        self.assertEqual(question, "报销制度的提交期限是什么？")
        messages = structured.invoke.call_args.args[0]
        self.assertIn(("user", "那期限呢？"), messages)
        self.assertIn(("user", "报销制度是什么？"), messages)


if __name__ == "__main__":
    unittest.main()
