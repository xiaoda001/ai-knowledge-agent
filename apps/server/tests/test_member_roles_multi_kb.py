import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession

from app.agents.knowledge_qa import graph
from app.agents.knowledge_qa.intent import ChatRoutePlan, PlannedChatTask
from app.agents.knowledge_qa import retrieval as retrieval_module
from app.api.routes import admin as admin_route
from app.api.routes import chat as chat_route
from app.api.routes import knowledge_bases as knowledge_bases_route
from app.api.routes import roles as roles_route
from app.api.schemas import ChatRequest, UserCreate, UserRolesUpdate
from app.services import legacy_roles
from server_core.db import Base
from server_core.models import (Chunk, Document, KnowledgeBase, KnowledgeBaseMember,
                                Role, User, UserRole)


class RequestSchemaTests(unittest.TestCase):
    def test_chat_accepts_multiple_ids_and_deduplicates_them(self):
        request = ChatRequest(knowledge_base_ids=["kb-a", "kb-b", "kb-a"], question="问题")
        self.assertEqual(request.knowledge_base_ids, ["kb-a", "kb-b"])

    def test_chat_keeps_legacy_single_id_compatibility(self):
        request = ChatRequest(knowledge_base_id="kb-old", question="问题")
        self.assertEqual(request.knowledge_base_ids, ["kb-old"])

    def test_chat_allows_empty_scope_for_non_retrieval_intents_and_caps_it_at_twenty(self):
        self.assertEqual(ChatRequest(question="你好").knowledge_base_ids, [])
        with self.assertRaises(ValidationError):
            ChatRequest(knowledge_base_ids=[f"kb-{n}" for n in range(21)], question="问题")

    def test_member_role_assignment_cannot_be_empty(self):
        with self.assertRaises(ValidationError):
            UserCreate(username="new", password="long-enough-password", department_id="d1",
                       clearance=0, role_ids=[])
        with self.assertRaises(ValidationError):
            UserRolesUpdate(role_ids=[])


class RetrievalFanoutTests(unittest.TestCase):
    @staticmethod
    def chunk(chunk_id, text):
        return SimpleNamespace(id=chunk_id, text=text, document_id=f"doc-{chunk_id}", ordinal=0)

    def test_retrieval_isolates_failed_kb_deduplicates_and_globally_reranks(self):
        db = Mock()
        user = object()
        a, b, c = (self.chunk(key, key) for key in "abc")
        calls = []

        def retrieve(_db, _user, kb_id, _question):
            calls.append(kb_id)
            if kb_id == "kb-fail":
                raise RuntimeError("temporary failure")
            return {"kb-a": [a, b], "kb-b": [b, c]}[kb_id]

        ranker = Mock()
        ranker.predict.return_value = [0.1, 0.2, 0.9]
        with patch.object(graph, "retrieve", side_effect=retrieve), patch.object(graph, "reranker", return_value=ranker):
            result = graph.retrieve_with_graph(db, user, ["kb-a", "kb-fail", "kb-b"], "question")

        self.assertEqual(calls, ["kb-a", "kb-fail", "kb-b"])
        self.assertEqual([chunk.id for chunk in result["chunks"]], ["c", "b", "a"])
        self.assertEqual(result["failed_knowledge_base_ids"], ["kb-fail"])
        db.expunge_all.assert_called_once_with()
        db.rollback.assert_called_once_with()

    def test_all_failed_kbs_return_no_chunks(self):
        db = Mock()
        with patch.object(graph, "retrieve", side_effect=RuntimeError("offline")), patch.object(
            graph, "reranker"
        ) as ranker:
            result = graph.retrieve_with_graph(db, object(), ["kb-a", "kb-b"], "question")

        self.assertEqual(result, {"chunks": [], "failed_knowledge_base_ids": ["kb-a", "kb-b"]})
        self.assertEqual(db.rollback.call_count, 2)
        ranker.assert_not_called()


class ChatPartialFailureTests(unittest.TestCase):
    class Query:
        def __init__(self, model, bases, documents):
            self.model = model
            self.bases = bases
            self.documents = documents

        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return self.bases if self.model is KnowledgeBase else self.documents

    class FakeDb:
        def __init__(self, bases, documents):
            self.bases = bases
            self.documents = documents

        def query(self, model):
            return ChatPartialFailureTests.Query(model, self.bases, self.documents)

    @staticmethod
    def collect(response):
        async def consume():
            return "".join([part.decode() if isinstance(part, bytes) else part
                            async for part in response.body_iterator])
        return asyncio.run(consume())

    def test_partial_retrieval_failure_is_reported_with_available_citations(self):
        kb_a = SimpleNamespace(id="kb-a", name="Alpha")
        kb_b = SimpleNamespace(id="kb-b", name="Beta")
        chunk = SimpleNamespace(id="chunk-1", document_id="doc-1", ordinal=2, text="evidence")
        document = SimpleNamespace(id="doc-1", knowledge_base_id="kb-a", filename="部门制度.md")
        db = self.FakeDb([kb_a, kb_b], [document])
        llm = Mock()
        llm.stream.return_value = [SimpleNamespace(content="answer [1]")]
        request = ChatRequest(knowledge_base_ids=["kb-a", "kb-b"], question="question")

        with patch.object(chat_route, "accessible_knowledge_bases", side_effect=lambda *_: db.bases), patch.object(
            chat_route, "retrieve_with_graph",
            return_value={"chunks": [chunk], "failed_knowledge_base_ids": ["kb-b"]},
        ), patch.object(chat_route, "llm_for_request", return_value=llm), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "_workspace_memory_message", return_value=None), patch.object(
            chat_route, "plan_chat_request", return_value=ChatRoutePlan(tasks=[
                PlannedChatTask(intent="knowledge_qa", question=request.question),
            ])):
            events = "".join(chat_route._chat_events(request, db, SimpleNamespace()))

        self.assertIn('"knowledge_base_name": "Alpha"', events)
        self.assertIn('"filename": "部门制度.md"', events)
        self.assertIn('"failed_knowledge_bases": [{"id": "kb-b", "name": "Beta"}]', events)
        self.assertIn("event: token", events)
        self.assertEqual(llm.stream.call_count, 1)

    def test_all_retrieval_failures_do_not_call_llm(self):
        bases = [SimpleNamespace(id=f"kb-{key}", name=key.upper()) for key in "ab"]
        db = self.FakeDb(bases, [])
        llm = Mock()
        request = ChatRequest(knowledge_base_ids=["kb-a", "kb-b"], question="question")

        with patch.object(chat_route, "accessible_knowledge_bases", side_effect=lambda *_: db.bases), patch.object(
            chat_route, "retrieve_with_graph",
            return_value={"chunks": [], "failed_knowledge_base_ids": ["kb-a", "kb-b"]},
        ), patch.object(chat_route, "llm_for_request", return_value=llm), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "_workspace_memory_message", return_value=None), patch.object(
            chat_route, "plan_chat_request", return_value=ChatRoutePlan(tasks=[
                PlannedChatTask(intent="knowledge_qa", question=request.question),
            ])):
            events = "".join(chat_route._chat_events(request, db, SimpleNamespace()))

        self.assertIn("相关知识库暂时无法检索", events)
        self.assertIn('"id": "kb-a", "name": "A"', events)
        llm.stream.assert_not_called()

    def test_unknown_or_unauthorized_kb_is_rejected_before_retrieval(self):
        db = self.FakeDb([SimpleNamespace(id="kb-a", name="Alpha")], [])
        request = ChatRequest(knowledge_base_ids=["kb-a", "kb-b"], question="question")

        with patch.object(chat_route, "accessible_knowledge_bases", side_effect=lambda *_: db.bases), patch.object(
            chat_route, "retrieve_with_graph"
        ) as retrieval, patch.object(chat_route, "llm_for_request", return_value=Mock()), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "plan_chat_request", return_value=ChatRoutePlan(tasks=[
            PlannedChatTask(intent="knowledge_qa", question=request.question),
        ])):
            events = "".join(chat_route._chat_events(request, db, SimpleNamespace()))

        self.assertIn("event: error", events)
        self.assertIn("所选知识库不存在或当前账号无权访问", events)
        retrieval.assert_not_called()

    def test_legacy_single_kb_request_preserves_source_token_and_done_sse_events(self):
        kb = SimpleNamespace(id="kb-a", name="Alpha")
        chunk = SimpleNamespace(id="chunk-1", document_id="doc-1", ordinal=0, text="source")
        document = SimpleNamespace(id="doc-1", knowledge_base_id="kb-a", filename="legacy.md")
        db = self.FakeDb([kb], [document])
        user = SimpleNamespace()
        llm = Mock()
        llm.stream.return_value = [SimpleNamespace(content="first [1]"), SimpleNamespace(content="second")]
        request = ChatRequest(knowledge_base_id="kb-a", question="question")

        with patch.object(chat_route, "accessible_knowledge_bases", side_effect=lambda *_: db.bases), patch.object(
            chat_route, "retrieve_with_graph",
            return_value={"chunks": [chunk], "failed_knowledge_base_ids": []},
        ) as retrieval, patch.object(chat_route, "llm_for_request", return_value=llm), patch.object(
            chat_route, "redact", side_effect=lambda value: value,
        ), patch.object(chat_route, "_workspace_memory_message", return_value=None), patch.object(
            chat_route, "plan_chat_request", return_value=ChatRoutePlan(tasks=[
                PlannedChatTask(intent="knowledge_qa", question=request.question),
            ])):
            events = "".join(chat_route._chat_events(request, db, user))

        retrieval.assert_called_once_with(db, user, ["kb-a"], "question")
        self.assertIn('"knowledge_base_name": "Alpha"', events)
        self.assertIn('"filename": "legacy.md"', events)
        self.assertIn('"failed_knowledge_bases": []', events)
        self.assertIn('"content": "first [1]"', events)
        self.assertIn('"content": "second"', events)
        self.assertIn("event: done", events)


class LegacyRoleMigrationTests(unittest.TestCase):
    class Connection:
        def __init__(self):
            self.commits = 0
            self.statements = []

        def execute(self, statement, _params=None):
            self.statements.append(str(statement))
            return SimpleNamespace(scalar=lambda: 1)

        def commit(self):
            self.commits += 1

        def close(self):
            pass

    class FakeSession:
        def __init__(self, state):
            self.state = state

        def get(self, model, _id):
            return self.state["role"] if model is Role else None

        def scalar(self, _statement):
            return None

        def scalars(self, _statement):
            users = self.state["users"] if not self.state["assigned"] else []
            return SimpleNamespace(all=lambda: users)

        def add(self, value):
            if isinstance(value, Role):
                self.state["role"] = value

        def add_all(self, values):
            self.state["assignments"].extend(values)
            self.state["assigned"] = bool(values) or self.state["assigned"]

        def flush(self):
            pass

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    def test_startup_migration_assigns_only_read_only_role_and_is_idempotent(self):
        user = SimpleNamespace(id="legacy-user")
        state = {"role": None, "users": [user], "assigned": False, "assignments": []}
        connection = self.Connection()
        with patch.object(legacy_roles.engine, "connect", return_value=connection), patch.object(
            legacy_roles, "Session", side_effect=lambda **_kwargs: self.FakeSession(state),
        ):
            legacy_roles.ensure_legacy_read_only_role()
            legacy_roles.ensure_legacy_read_only_role()

        self.assertEqual(state["role"].id, legacy_roles.LEGACY_READ_ONLY_ROLE_ID)
        self.assertEqual(set(state["role"].permissions), {"chat.use", "document.read"})
        self.assertEqual(len(state["assignments"]), 1)
        self.assertEqual(state["assignments"][0].user_id, "legacy-user")
        self.assertEqual(state["assignments"][0].role_id, legacy_roles.LEGACY_READ_ONLY_ROLE_ID)
        self.assertEqual(sum("GET_LOCK" in sql for sql in connection.statements), 2)


class DocumentAclRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = OrmSession(self.engine)
        user = User(id="member-1", username="member", password_hash="x", department_id="dept-a",
                    clearance=2, active=True, is_admin=False)
        reader = Role(id="role-reader", name="Reader", permissions=["chat.use", "document.read"])
        other = Role(id="role-other", name="Other", permissions=["chat.use"])
        kb = KnowledgeBase(id="kb-1", name="KB 1", created_by=user.id)
        self.db.add_all([user, reader, other, kb])
        self.db.flush()
        self.db.add_all([
            UserRole(user_id=user.id, role_id=reader.id),
            KnowledgeBaseMember(knowledge_base_id=kb.id, user_id=user.id),
        ])
        documents = [
            Document(id="doc-allowed", knowledge_base_id=kb.id, filename="allowed.md", storage_path="/allowed",
                     status="ready", department_id="dept-a", classification_level=1, allowed_roles=[]),
            Document(id="doc-high", knowledge_base_id=kb.id, filename="high.md", storage_path="/high",
                     status="ready", department_id="dept-a", classification_level=3, allowed_roles=[]),
            Document(id="doc-dept", knowledge_base_id=kb.id, filename="dept.md", storage_path="/dept",
                     status="ready", department_id="dept-b", classification_level=1, allowed_roles=[]),
            Document(id="doc-role-denied", knowledge_base_id=kb.id, filename="role.md", storage_path="/role",
                     status="ready", department_id="dept-a", classification_level=1,
                     allowed_roles=["Other"]),
            Document(id="doc-role-allowed", knowledge_base_id=kb.id, filename="reader.md",
                     storage_path="/reader", status="ready", department_id="dept-a",
                     classification_level=1, allowed_roles=["Reader"]),
            Document(id="doc-missing-acl", knowledge_base_id=kb.id, filename="missing.md",
                     storage_path="/missing", status="ready", department_id="dept-a",
                     classification_level=None, allowed_roles=[]),
            Document(id="doc-pending", knowledge_base_id=kb.id, filename="pending.md",
                     storage_path="/pending", status="queued", department_id="dept-a",
                     classification_level=1, allowed_roles=[]),
        ]
        self.db.add_all(documents)
        self.db.add_all([
            Chunk(id="chunk-allowed", document_id="doc-allowed", text="allowed evidence", ordinal=0),
            Chunk(id="chunk-high", document_id="doc-high", text="high evidence", ordinal=0),
            Chunk(id="chunk-dept", document_id="doc-dept", text="department evidence", ordinal=0),
            Chunk(id="chunk-role-denied", document_id="doc-role-denied", text="secret evidence", ordinal=0),
            Chunk(id="chunk-role-allowed", document_id="doc-role-allowed", text="reader evidence", ordinal=0),
            Chunk(id="chunk-missing", document_id="doc-missing-acl", text="missing evidence", ordinal=0),
            Chunk(id="chunk-pending", document_id="doc-pending", text="pending evidence", ordinal=0),
        ])
        self.db.commit()
        self.user = self.db.get(User, "member-1")

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_department_clearance_role_and_ready_filters_apply_before_retrieval(self):
        with patch.object(retrieval_module.chromadb, "HttpClient") as http_client, patch.object(
            retrieval_module, "embed_texts", return_value=[[0.1, 0.2]],
        ), patch.object(retrieval_module, "reranker") as reranker:
            collection = http_client.return_value.get_collection.return_value
            collection.query.return_value = {"ids": [["chunk-allowed", "chunk-role-allowed",
                                                       "chunk-high", "chunk-dept", "chunk-role-denied"]]}
            reranker.return_value.predict.return_value = [0.9, 0.8]

            allowed_documents = retrieval_module.authorized_documents(self.db, self.user, "kb-1")
            chunks = retrieval_module.retrieve(self.db, self.user, "kb-1", "evidence")

        self.assertEqual({doc.id for doc in allowed_documents}, {"doc-allowed", "doc-role-allowed"})
        self.assertEqual({chunk.id for chunk in chunks}, {"chunk-allowed", "chunk-role-allowed"})
        dense_filter = collection.query.call_args.kwargs["where"]
        self.assertEqual(set(dense_filter["document_id"]["$in"]), {"doc-allowed", "doc-role-allowed"})

    def test_non_member_gets_no_candidates_and_never_queries_vector_store(self):
        with patch.object(retrieval_module.chromadb, "HttpClient") as http_client:
            self.assertEqual(retrieval_module.retrieve(self.db, self.user, "other-kb", "evidence"), [])
        http_client.assert_not_called()


class MemberAndRoleRouteTests(unittest.TestCase):
    class FakeDb:
        def __init__(self, roles=None, existing_membership=False, system_role=None):
            self.roles = roles or []
            self.existing_membership = existing_membership
            self.system_role = system_role
            self.added = []
            self.commits = 0

        def scalar(self, _statement):
            return "membership-id" if self.existing_membership else None

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: self.roles)

        def get(self, model, object_id):
            if model is Role and self.system_role and object_id == self.system_role.id:
                return self.system_role
            if model is KnowledgeBase:
                return SimpleNamespace(id=object_id)
            if model is User:
                return SimpleNamespace(id=object_id)
            return None

        def add(self, value):
            self.added.append(value)

        def add_all(self, values):
            self.added.extend(values)

        def flush(self):
            for value in self.added:
                if isinstance(value, User):
                    value.id = "new-user-id"

        def commit(self):
            self.commits += 1

    def test_account_creation_requires_role_and_does_not_join_a_knowledge_base(self):
        selected_role = Role(id="role-reader", name="问答者", permissions=["chat.use"])
        db = self.FakeDb(roles=[selected_role])
        actor = SimpleNamespace(is_admin=True)
        payload = UserCreate(username=" member ", password="long-enough-password", department_id=" dept ",
                             clearance=0, role_ids=["role-reader"])

        with patch.object(admin_route, "password_hash", return_value="hashed"):
            result = admin_route.create_user(payload, db, actor)

        created_user = next(value for value in db.added if isinstance(value, User))
        membership_rows = [value for value in db.added if isinstance(value, KnowledgeBaseMember)]
        role_rows = [value for value in db.added if isinstance(value, UserRole)]
        self.assertEqual(result, {"id": "new-user-id", "username": "member"})
        self.assertEqual(created_user.department_id, "dept")
        self.assertEqual(len(role_rows), 1)
        self.assertEqual(role_rows[0].role_id, "role-reader")
        self.assertEqual(membership_rows, [])
        self.assertEqual(db.commits, 1)

    def test_member_manage_operator_can_add_existing_account_to_a_kb(self):
        db = self.FakeDb()
        actor = SimpleNamespace(is_admin=True)

        with patch.object(knowledge_bases_route, "is_kb_member", return_value=True):
            result = knowledge_bases_route.add_member("kb-target", "existing-user", db, actor)

        membership = next(value for value in db.added if isinstance(value, KnowledgeBaseMember))
        self.assertEqual(result, {"status": "added"})
        self.assertEqual(membership.knowledge_base_id, "kb-target")
        self.assertEqual(membership.user_id, "existing-user")
        self.assertEqual(db.commits, 1)

    def test_adding_existing_kb_member_is_idempotent(self):
        db = self.FakeDb(existing_membership=True)
        with patch.object(knowledge_bases_route, "is_kb_member", return_value=True):
            result = knowledge_bases_route.add_member("kb-target", "existing-user", db,
                                                      SimpleNamespace(is_admin=True))
        self.assertEqual(result, {"status": "already_member"})
        self.assertEqual(db.added, [])
        self.assertEqual(db.commits, 0)

    def test_reserved_compatibility_role_cannot_be_edited(self):
        system_role = Role(id=legacy_roles.LEGACY_READ_ONLY_ROLE_ID,
                           name=legacy_roles.LEGACY_READ_ONLY_ROLE_NAME,
                           permissions=["chat.use", "document.read"])
        db = self.FakeDb(system_role=system_role)
        with self.assertRaises(roles_route.HTTPException) as raised:
            roles_route.update_role(system_role.id, roles_route.RoleUpdate(description="changed", permissions=[]),
                                    db, SimpleNamespace(is_admin=True))
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(system_role.description, None)
        self.assertEqual(db.commits, 0)


if __name__ == "__main__":
    unittest.main()
