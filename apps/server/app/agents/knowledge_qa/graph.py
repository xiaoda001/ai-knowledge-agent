import json
import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from opentelemetry.trace import Status, StatusCode
from sqlalchemy import select

from app.agents.knowledge_qa.retrieval import retrieve, rerank_document_text, reranker
from app.agents.providers.redaction import redact_for_observability
from server_core.config import settings
from server_core.document_versions import document_version_states
from server_core.models import Document
from server_core.observability import tracer


logger = logging.getLogger(__name__)
_tracer = tracer(__name__)


class QueryState(TypedDict, total=False):
    db: object
    user: object
    kb_id: str
    question: str
    include_history: bool
    chunks: list


def retrieve_with_graph(db, user, kb_ids: list[str], question: str, include_history: bool = False,
                        trace_context=None):
    graph = StateGraph(QueryState)
    def retrieve_node(state):
        history_kwargs = {"include_history": True} if state.get("include_history") else {}
        return {"chunks": retrieve(
            state["db"], state["user"], state["kb_id"], state["question"], **history_kwargs,
        )}

    graph.add_node("authorized_hybrid_retrieval", retrieve_node)
    graph.add_edge(START, "authorized_hybrid_retrieval")
    graph.add_edge("authorized_hybrid_retrieval", END)
    compiled = graph.compile()
    per_knowledge_base = []
    failed_knowledge_base_ids = []
    for kb_id in kb_ids:
        with _tracer.start_as_current_span("knowledge.retrieval", context=trace_context) as span:
            span.set_attribute("langfuse.observation.type", "retriever")
            try:
                chunks = compiled.invoke({
                    "db": db, "user": user, "kb_id": kb_id, "question": question,
                    "include_history": include_history,
                })["chunks"]
                per_knowledge_base.append(chunks)
                span.set_attribute("retrieval.chunk_count", len(chunks))
                if settings.langfuse_capture_content:
                    span.set_attribute("langfuse.observation.input", json.dumps({
                        "question": redact_for_observability(question), "knowledge_base_id": kb_id,
                    }, ensure_ascii=False))
                    span.set_attribute("langfuse.observation.output", json.dumps([
                        {"chunk_id": chunk.id, "document_id": chunk.document_id,
                         "ordinal": chunk.ordinal, "text": redact_for_observability(chunk.text[:2000])}
                        for chunk in chunks
                    ], ensure_ascii=False))
            except Exception as exc:
                db.expunge_all()
                db.rollback()
                logger.warning("Knowledge-base retrieval failed (%s)", type(exc).__name__)
                failed_knowledge_base_ids.append(kb_id)
                span.set_attribute("retrieval.failed", True)
                span.set_status(Status(StatusCode.ERROR))

    # Rerank the combined candidates together, then keep the existing eight-source budget.
    candidates = []
    seen_chunk_ids = set()
    for items in per_knowledge_base:
        for chunk in items:
            if chunk.id not in seen_chunk_ids:
                candidates.append(chunk)
                seen_chunk_ids.add(chunk.id)
    if candidates:
        documents_by_id = {}
        version_states = {}
        try:
            candidate_document_ids = {chunk.document_id for chunk in candidates}
            candidate_documents = db.scalars(
                select(Document).where(Document.id.in_(candidate_document_ids))
            ).all()
            knowledge_base_ids = {document.knowledge_base_id for document in candidate_documents}
            version_documents = db.scalars(
                select(Document).where(
                    Document.knowledge_base_id.in_(knowledge_base_ids),
                    Document.status.in_({"ready", "expired"}),
                )
            ).all() if knowledge_base_ids else candidate_documents
            documents_by_id = {document.id: document for document in candidate_documents}
            version_states = document_version_states(version_documents)
        except Exception:
            logger.warning("Could not load document version metadata for reranking")
        with _tracer.start_as_current_span("knowledge.rerank", context=trace_context) as span:
            span.set_attribute("langfuse.observation.type", "retriever")
            rerank_candidates = candidates
            rerank_inputs = [
                (question, rerank_document_text(
                    chunk, documents_by_id.get(chunk.document_id), version_states.get(chunk.document_id),
                ))
                for chunk in candidates
            ]
            scores = reranker().predict(rerank_inputs)
            candidates = [chunk for _, chunk in sorted(zip(scores, candidates), key=lambda item: item[0], reverse=True)[:8]]
            span.set_attribute("retrieval.candidate_count", len(seen_chunk_ids))
            span.set_attribute("retrieval.result_count", len(candidates))
            if settings.langfuse_capture_content:
                span.set_attribute("langfuse.observation.input", json.dumps({
                    "question": redact_for_observability(question),
                    "candidates": [{"chunk_id": chunk.id,
                                    "text": redact_for_observability(rerank_input[1][:2000])}
                                   for chunk, rerank_input in zip(rerank_candidates, rerank_inputs)],
                }, ensure_ascii=False))
                span.set_attribute("langfuse.observation.output", json.dumps([
                    {"chunk_id": chunk.id, "text": redact_for_observability(chunk.text[:2000])}
                    for chunk in candidates
                ], ensure_ascii=False))
    return {"chunks": candidates, "failed_knowledge_base_ids": failed_knowledge_base_ids}
