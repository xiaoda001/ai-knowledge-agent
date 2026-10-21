import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.agents.knowledge_qa.intent import ChatRoutePlan, PlannedChatTask
from app.api.routes import chat as chat_route
from app.api.schemas import ChatRequest
from server_core.db import Base
from server_core.models import ChatConversation, ChatMessage, User


class ChatHistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(id="user-a", username="a", password_hash="x")
        self.other = User(id="user-b", username="b", password_hash="x")
        self.db.add_all([self.user, self.other])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @staticmethod
    def collect(response):
        async def consume():
            parts = [part.decode() if isinstance(part, bytes) else part
                     async for part in response.body_iterator]
            return "".join(parts)
        return asyncio.run(consume())

    @staticmethod
    def post_chat(payload, db, user):
        body = payload.model_dump_json().encode()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request({
            "type": "http", "method": "POST", "path": "/chat", "headers": [
                (b"content-type", b"application/json"),
            ], "query_string": b"", "server": ("test", 80), "client": ("test", 1),
            "scheme": "http",
        }, receive)
        return asyncio.run(chat_route.chat(request, db, user))

    def test_successful_turns_are_saved_and_reused_as_server_context(self):
        conversation = chat_route.create_conversation(self.db, self.user)
        llm = Mock()
        llm.stream.return_value = [SimpleNamespace(content="你好"), SimpleNamespace(content="！")]
        usage = {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16,
                 "tokens_estimated": False, "cost_usd": 0.0001, "pricing_configured": True}
        with patch.object(chat_route, "llm_for_request", return_value=llm), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "plan_chat_request", return_value=ChatRoutePlan(tasks=[
            PlannedChatTask(intent="casual_chat", question="我刚才说了什么？"),
        ])), patch.object(chat_route, "ChatUsageTracker", return_value=Mock(snapshot=lambda: usage)):
            first_events = self.collect(self.post_chat(
                ChatRequest(question="你好", conversation_id=conversation["id"]), self.db, self.user,
            ))
            self.assertIn('event: usage', first_events)
            llm.stream.return_value = [SimpleNamespace(content="我刚才问了你好。")]
            self.collect(self.post_chat(ChatRequest(question="我刚才说了什么？",
                                                    conversation_id=conversation["id"]), self.db, self.user))

        saved = chat_route.get_conversation(conversation["id"], self.db, self.user)
        self.assertEqual([item["role"] for item in saved["messages"]],
                         ["user", "assistant", "user", "assistant"])
        self.assertEqual(saved["messages"][0]["content"], "你好")
        self.assertEqual(saved["messages"][1]["content"], "你好！")
        self.assertEqual(saved["messages"][1]["usage"], usage)
        model_messages = llm.stream.call_args.args[0]
        self.assertIn(("assistant", "你好！"), model_messages)

    def test_other_user_cannot_read_or_chat_in_conversation(self):
        conversation = ChatConversation(user_id=self.user.id, title="private")
        self.db.add(conversation)
        self.db.commit()

        with self.assertRaises(HTTPException) as detail:
            chat_route.get_conversation(conversation.id, self.db, self.other)
        self.assertEqual(detail.exception.status_code, 404)
        with self.assertRaises(HTTPException) as chat_error:
            self.post_chat(ChatRequest(question="hello", conversation_id=conversation.id), self.db, self.other)
        self.assertEqual(chat_error.exception.status_code, 404)
        self.assertEqual(self.db.query(ChatMessage).filter_by(conversation_id=conversation.id).count(), 0)

    def test_failed_generation_does_not_mark_user_turn_as_context(self):
        conversation = chat_route.create_conversation(self.db, self.user)
        llm = Mock()
        llm.stream.side_effect = RuntimeError("offline")
        with patch.object(chat_route, "llm_for_request", return_value=llm), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ):
            self.collect(self.post_chat(ChatRequest(question="你好", conversation_id=conversation["id"]),
                                        self.db, self.user))

        saved = chat_route.get_conversation(conversation["id"], self.db, self.user)
        self.assertEqual(len(saved["messages"]), 1)
        self.assertFalse(self.db.query(ChatMessage).first().complete)


if __name__ == "__main__":
    unittest.main()
