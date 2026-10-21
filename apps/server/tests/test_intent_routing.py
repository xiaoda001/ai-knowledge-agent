import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agents.knowledge_qa.intent import (
    ChatIntent, ChatRoutePlan, PlannedChatTask, plan_chat_request,
)
from app.api.routes import chat as chat_route
from app.api.schemas import ChatRequest
from app.services.chat_system_queries import (
    accessible_knowledge_bases, count_accessible_knowledge_bases, count_visible_documents,
)
from server_core.db import Base
from server_core.models import Document, KnowledgeBase, KnowledgeBaseMember, Role, User, UserRole


class ChatRouteTests(unittest.TestCase):
    @staticmethod
    def events(response):
        return "".join(part.decode() if isinstance(part, bytes) else part for part in response)

    def test_casual_chat_works_without_selected_knowledge_bases(self):
        llm = Mock()
        llm.stream.return_value = [SimpleNamespace(content="你好！")]
        request = ChatRequest(question="你好")
        with patch.object(chat_route, "llm_for_request", return_value=llm), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(
            chat_route, "retrieve_with_graph",
        ) as retrieve:
            response = chat_route._chat_events(request, Mock(), SimpleNamespace())
            events = self.events(response)

        retrieve.assert_not_called()
        self.assertIn('event: sources', events)
        self.assertIn('"content": "你好！"', events)
        self.assertIn('event: done', events)

    def test_system_counts_use_authorized_service_and_skip_retrieval(self):
        request = ChatRequest(question="我能访问几个知识库？")
        user = SimpleNamespace(id="u1")
        with patch.object(chat_route, "llm_for_request", return_value=Mock()), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "plan_chat_request", return_value=ChatRoutePlan(tasks=[
            PlannedChatTask(intent="system_query", question=request.question,
                            system_query="count_accessible_knowledge_bases"),
        ])), patch.object(chat_route, "count_accessible_knowledge_bases", return_value=3) as count, patch.object(
            chat_route, "accessible_knowledge_bases", return_value=[],
        ), patch.object(
            chat_route, "retrieve_with_graph",
        ) as retrieve:
            response = chat_route._chat_events(request, Mock(), user)
            events = self.events(response)

        count.assert_called_once()
        retrieve.assert_not_called()
        self.assertIn("你目前可以访问 3 个知识库", events)

    def test_list_accessible_knowledge_bases_uses_system_query_without_retrieval(self):
        request = ChatRequest(question="我可以访问哪些知识库？")
        user = SimpleNamespace(id="u1")
        route_plan = ChatRoutePlan(tasks=[
            PlannedChatTask(intent="system_query", question=request.question,
                            system_query="list_accessible_knowledge_bases"),
        ])
        bases = [SimpleNamespace(id="kb1", name="电商规则", description="售后"),
                 SimpleNamespace(id="kb2", name="售后流程", description="退换货")]
        with patch.object(chat_route, "llm_for_request", return_value=Mock()), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "plan_chat_request", return_value=route_plan), patch.object(
            chat_route, "accessible_knowledge_bases", return_value=bases,
        ) as list_bases, patch.object(chat_route, "retrieve_with_graph") as retrieve:
            events = self.events(chat_route._chat_events(request, Mock(), user))

        list_bases.assert_called_once()
        retrieve.assert_not_called()
        self.assertIn("你可以访问以下 2 个知识库：电商规则、售后流程", events)

    def test_knowledge_question_without_manual_scope_uses_authorized_knowledge_bases(self):
        request = ChatRequest(question="报销制度是什么？")
        with patch.object(chat_route, "llm_for_request", return_value=Mock()), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "plan_chat_request", return_value=ChatRoutePlan(tasks=[
            PlannedChatTask(intent="knowledge_qa", question=request.question),
        ])), patch.object(chat_route, "accessible_knowledge_bases", return_value=[]), patch.object(
            chat_route, "retrieve_with_graph",
        ) as retrieve:
            response = chat_route._chat_events(request, Mock(), SimpleNamespace())
            events = self.events(response)

        retrieve.assert_not_called()
        self.assertIn("没有可访问的知识库", events)

    def test_finance_question_is_routed_to_authorized_finance_base_without_manual_selection(self):
        request = ChatRequest(question="财务规则有什么特别注意的？")
        user = SimpleNamespace(id="u1")
        finance = SimpleNamespace(id="finance-id", name="财务与采购", description="差旅与费用报销")
        product = SimpleNamespace(id="product-id", name="产品支持", description="保修和维修")
        document = SimpleNamespace(id="finance-doc", knowledge_base_id="finance-id", filename="报销规则.md")
        chunk = SimpleNamespace(id="finance-chunk", document_id="finance-doc", ordinal=0,
                                text="报销需要审批。")
        db = Mock()
        db.query.return_value.filter.return_value.all.return_value = [document]
        llm = Mock()
        llm.stream.return_value = [SimpleNamespace(content="财务报销需要审批 [1]。")]
        plan = ChatRoutePlan(tasks=[PlannedChatTask(
            intent="knowledge_qa", question=request.question, knowledge_base_refs=["kb_1"],
        )])

        with patch.object(chat_route, "accessible_knowledge_bases", return_value=[finance, product]), patch.object(
            chat_route, "llm_for_request", return_value=llm,
        ), patch.object(chat_route, "redact", side_effect=lambda value: value), patch.object(
            chat_route, "plan_chat_request", return_value=plan,
        ) as planner, patch.object(chat_route, "retrieve_with_graph", return_value={
            "chunks": [chunk], "failed_knowledge_base_ids": [],
        }) as retrieve, patch.object(chat_route, "_workspace_memory_message", return_value=None):
            events = self.events(chat_route._chat_events(request, db, user))

        catalog = planner.call_args.args[-1]
        self.assertEqual([item["name"] for item in catalog], ["财务与采购", "产品支持"])
        retrieve.assert_called_once_with(db, user, ["finance-id"], request.question)
        source_events = [line.removeprefix("data: ") for line in events.splitlines()
                         if line.startswith("data: ") and '"sources"' in line]
        self.assertEqual(len(source_events), 1)
        self.assertIn('"knowledge_base_name": "财务与采购"', source_events[0])
        self.assertNotIn("产品支持", source_events[0])

    def test_legacy_explicit_scope_can_only_narrow_automatic_authorized_scope(self):
        finance = SimpleNamespace(id="finance-id", name="财务与采购", description="报销")
        product = SimpleNamespace(id="product-id", name="产品支持", description="保修")
        request = ChatRequest(question="制度是什么？", knowledge_base_ids=["finance-id"])
        user = SimpleNamespace(id="u1")
        db = Mock()
        db.query.return_value.filter.return_value.all.return_value = []
        llm = Mock()
        llm.stream.return_value = [SimpleNamespace(content="回答 [1]")]
        plan = ChatRoutePlan(tasks=[PlannedChatTask(intent="knowledge_qa", question=request.question)])

        with patch.object(chat_route, "accessible_knowledge_bases", return_value=[finance, product]), patch.object(
            chat_route, "llm_for_request", return_value=llm,
        ), patch.object(chat_route, "redact", side_effect=lambda value: value), patch.object(
            chat_route, "plan_chat_request", return_value=plan,
        ), patch.object(chat_route, "retrieve_with_graph", return_value={
            "chunks": [], "failed_knowledge_base_ids": [],
        }) as retrieve:
            self.events(chat_route._chat_events(request, db, user))

        retrieve.assert_called_once_with(db, user, ["finance-id"], request.question)

    def test_compound_knowledge_questions_are_routed_to_separate_authorized_bases(self):
        request = ChatRequest(question="出差怎么报销？产品保修多久？")
        user = SimpleNamespace(id="u1")
        finance = SimpleNamespace(id="finance-id", name="财务与采购", description="差旅报销")
        product = SimpleNamespace(id="product-id", name="产品支持", description="保修时长")
        finance_document = SimpleNamespace(id="doc-finance", knowledge_base_id="finance-id", filename="差旅.md")
        product_document = SimpleNamespace(id="doc-product", knowledge_base_id="product-id", filename="保修.md")
        finance_chunk = SimpleNamespace(id="chunk-finance", document_id="doc-finance", ordinal=0,
                                        text="报销需审批。")
        product_chunk = SimpleNamespace(id="chunk-product", document_id="doc-product", ordinal=0,
                                        text="保修两年。")
        db = Mock()
        db.query.return_value.filter.return_value.all.return_value = [finance_document, product_document]
        llm = Mock()
        llm.stream.side_effect = [
            [SimpleNamespace(content="出差报销需要审批 [1]。")],
            [SimpleNamespace(content="产品保修两年 [2]。")],
        ]
        plan = ChatRoutePlan(tasks=[
            PlannedChatTask(intent="knowledge_qa", question="出差怎么报销？", knowledge_base_refs=["kb_1"]),
            PlannedChatTask(intent="knowledge_qa", question="产品保修多久？", knowledge_base_refs=["kb_2"]),
        ])
        retrieve_result = {
            "finance-id": {"chunks": [finance_chunk], "failed_knowledge_base_ids": []},
            "product-id": {"chunks": [product_chunk], "failed_knowledge_base_ids": []},
        }
        memory_scopes = []

        with patch.object(chat_route, "accessible_knowledge_bases", return_value=[finance, product]), patch.object(
            chat_route, "llm_for_request", return_value=llm,
        ), patch.object(chat_route, "redact", side_effect=lambda value: value), patch.object(
            chat_route, "plan_chat_request", return_value=plan,
        ), patch.object(chat_route, "retrieve_with_graph", side_effect=lambda _db, _user, ids, _question:
                      retrieve_result[ids[0]]) as retrieve, patch.object(
            chat_route, "_workspace_memory_message",
            side_effect=lambda _db, _user, ids: memory_scopes.append(ids) or None,
        ):
            events = self.events(chat_route._chat_events(request, db, user))

        self.assertEqual([call.args[2] for call in retrieve.call_args_list], [["finance-id"], ["product-id"]])
        self.assertEqual(memory_scopes, [["finance-id"], ["product-id"]])
        self.assertIn('"chunk_id": "chunk-finance"', events)
        self.assertIn('"chunk_id": "chunk-product"', events)
        self.assertIn('"source_number": 2', events)

    def test_compound_question_splits_system_count_and_authorized_knowledge_qa(self):
        request = ChatRequest(
            question="统计知识库数量并告诉我出差如何报销",
            knowledge_base_ids=["kb1"],
        )
        user = SimpleNamespace(id="u1")
        kb = SimpleNamespace(id="kb1", name="财务与采购", description="差旅和费用报销")
        document = SimpleNamespace(id="doc1", knowledge_base_id="kb1", filename="差旅制度.md")
        chunk = SimpleNamespace(id="chunk1", document_id="doc1", ordinal=0,
                                text="员工应在返程后十个工作日内提交报销单。")
        db = Mock()

        def query(model):
            if model is KnowledgeBase:
                return SimpleNamespace(filter=lambda *_: SimpleNamespace(all=lambda: [kb]))
            if model is Document:
                return SimpleNamespace(filter=lambda *_: SimpleNamespace(all=lambda: [document]))
            self.fail(f"Unexpected database query: {model}")

        db.query.side_effect = query
        llm = Mock()
        llm.stream.return_value = [SimpleNamespace(content="返程后十个工作日内提交报销单 [1]。")]
        executed = []
        route_plan = ChatRoutePlan(tasks=[
            PlannedChatTask(intent="system_query", question="我可以访问多少个知识库？",
                            system_query="count_accessible_knowledge_bases"),
            PlannedChatTask(intent="knowledge_qa", question="出差如何报销？"),
        ])
        with patch.object(chat_route, "llm_for_request", return_value=llm), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "plan_chat_request", return_value=route_plan) as planner, patch.object(
            chat_route, "count_accessible_knowledge_bases", side_effect=lambda *_: executed.append("system") or 5,
        ) as count, patch.object(chat_route, "accessible_knowledge_bases", return_value=[kb]), patch.object(
            chat_route, "_workspace_memory_message", return_value=None,
        ), patch.object(
            chat_route, "retrieve_with_graph", side_effect=lambda *_: (
                executed.append("knowledge"), {"chunks": [chunk], "failed_knowledge_base_ids": []},
            )[1],
        ) as retrieve:
            response = chat_route._chat_events(request, db, user)
            events = self.events(response)

        planner.assert_called_once()
        count.assert_called_once_with(db, user)
        retrieve.assert_called_once_with(db, user, ["kb1"], "出差如何报销？")
        self.assertIn("你目前可以访问 5 个知识库", events)
        self.assertIn("返程后十个工作日内提交报销单 [1]", events)
        self.assertIn('"knowledge_base_name": "财务与采购"', events)
        self.assertEqual(executed, ["system", "knowledge"])
        self.assertIn("event: done", events)

    def test_compound_question_without_manual_scope_handles_empty_authorized_scope(self):
        request = ChatRequest(question="我有几个知识库？出差如何报销？")
        plan = ChatRoutePlan(tasks=[
            PlannedChatTask(intent="system_query", question="我有几个知识库？",
                            system_query="count_accessible_knowledge_bases"),
            PlannedChatTask(intent="knowledge_qa", question="出差如何报销？"),
        ])
        with patch.object(chat_route, "llm_for_request", return_value=Mock()), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "plan_chat_request", return_value=plan), patch.object(
            chat_route, "count_accessible_knowledge_bases", return_value=2,
        ), patch.object(chat_route, "accessible_knowledge_bases", return_value=[]), patch.object(
            chat_route, "retrieve_with_graph",
        ) as retrieve:
            response = chat_route._chat_events(request, Mock(), SimpleNamespace(id="u1"))
            events = self.events(response)

        retrieve.assert_not_called()
        self.assertIn("你目前可以访问 2 个知识库", events)
        self.assertIn("没有可访问的知识库", events)
        self.assertIn("event: done", events)

    def test_compound_question_does_not_retrieve_from_unauthorized_scope(self):
        request = ChatRequest(question="我有几个知识库？出差如何报销？", knowledge_base_ids=["private"])
        plan = ChatRoutePlan(tasks=[
            PlannedChatTask(intent="system_query", question="我有几个知识库？",
                            system_query="count_accessible_knowledge_bases"),
            PlannedChatTask(intent="knowledge_qa", question="出差如何报销？"),
        ])
        db = Mock()
        db.query.return_value.filter.return_value.all.return_value = []
        user = SimpleNamespace(id="u1")
        with patch.object(chat_route, "llm_for_request", return_value=Mock()), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "plan_chat_request", return_value=plan), patch.object(
            chat_route, "count_accessible_knowledge_bases", return_value=2,
        ), patch.object(chat_route, "accessible_knowledge_bases", return_value=[]), patch.object(
            chat_route, "retrieve_with_graph",
        ) as retrieve:
            response = chat_route._chat_events(request, db, user)
            events = self.events(response)

        retrieve.assert_not_called()
        self.assertIn("你目前可以访问 2 个知识库", events)
        self.assertIn("所选知识库不存在或当前账号无权访问", events)


class CompoundIntentPlanTests(unittest.TestCase):
    def test_plan_schema_limits_task_count_and_route_operations(self):
        tasks = [PlannedChatTask(intent="clarify", question=f"问题 {index}") for index in range(7)]
        with self.assertRaises(ValueError):
            ChatRoutePlan(tasks=tasks)
        with self.assertRaises(ValueError):
            PlannedChatTask(intent="system_query", question="统计数量")
        self.assertEqual(len(ChatRoutePlan(tasks=[
            PlannedChatTask(intent="knowledge_qa", question="售后注意事项"),
        ]).tasks), 1)

    def test_route_planner_is_used_for_compounds_without_punctuation(self):
        planned = ChatRoutePlan(tasks=[
            PlannedChatTask(intent="system_query", question="统计知识库数量",
                            system_query="count_accessible_knowledge_bases"),
            PlannedChatTask(intent="knowledge_qa", question="售后注意事项"),
        ])
        llm = Mock()
        llm.with_structured_output.return_value.invoke.return_value = planned

        result = plan_chat_request(llm, "统计知识库数量并告诉我售后注意事项", [])

        self.assertEqual(len(result.tasks), 2)
        prompt = llm.with_structured_output.return_value.invoke.call_args.args[0]
        self.assertIn("不要只依据问号", prompt[0][1])
        self.assertIn("多个请求写在同一句或没有标点", prompt[0][1])

class AuthorizedSystemQueryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(id="u1", username="member", password_hash="x", department_id="d1",
                         clearance=1, active=True, is_admin=False)
        self.other = User(id="u2", username="other", password_hash="x", department_id="d1",
                          clearance=1, active=True, is_admin=False)
        self.role = Role(id="r1", name="Reader", permissions=["chat.use", "document.read"])
        self.kb = KnowledgeBase(id="kb1", name="Alpha", created_by="u1")
        self.other_kb = KnowledgeBase(id="kb2", name="Private", created_by="u2")
        self.db.add_all([self.user, self.other, self.role, self.kb, self.other_kb])
        self.db.flush()
        self.db.add_all([
            UserRole(user_id="u1", role_id="r1"),
            KnowledgeBaseMember(knowledge_base_id="kb1", user_id="u1"),
            KnowledgeBaseMember(knowledge_base_id="kb2", user_id="u2"),
            Document(id="visible", knowledge_base_id="kb1", filename="visible.md", storage_path="/v",
                     status="ready", department_id="d1", classification_level=1, allowed_roles=[]),
            Document(id="hidden", knowledge_base_id="kb1", filename="hidden.md", storage_path="/h",
                     status="ready", department_id="d2", classification_level=1, allowed_roles=[]),
            Document(id="pending", knowledge_base_id="kb1", filename="pending.md", storage_path="/p",
                     status="queued", department_id="d1", classification_level=1, allowed_roles=[]),
        ])
        self.db.commit()
        self.user = self.db.get(User, "u1")

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_count_only_includes_knowledge_bases_where_user_is_member(self):
        self.assertEqual(count_accessible_knowledge_bases(self.db, self.user), 1)

    def test_list_accessible_knowledge_bases_only_returns_membership_scope(self):
        bases = accessible_knowledge_bases(self.db, self.user)
        self.assertEqual([base.name for base in bases], ["Alpha"])
        self.assertEqual(chat_route._route_system_query(ChatIntent(
            intent="system_query", system_query="list_accessible_knowledge_bases",
        ), self.db, self.user), "你可以访问以下 1 个知识库：Alpha。")

    def test_document_count_reuses_acl_and_excludes_unready_documents(self):
        self.assertEqual(count_visible_documents(self.db, self.user, " alpha "), 1)

    def test_unavailable_knowledge_base_has_no_distinguishable_count(self):
        self.assertIsNone(count_visible_documents(self.db, self.user, "Private"))
        self.assertIsNone(count_visible_documents(self.db, self.user, "Missing"))


if __name__ == "__main__":
    unittest.main()
