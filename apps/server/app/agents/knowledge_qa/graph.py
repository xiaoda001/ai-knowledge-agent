import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.knowledge_qa.retrieval import retrieve, reranker
from server_core.observability import tracer


logger = logging.getLogger(__name__)
_tracer = tracer(__name__)


class QueryState(TypedDict, total=False):
    db: object
    user: object
    kb_id: str
    question: str
    chunks: list


def retrieve_with_graph(db, user, kb_ids: list[str], question: str):
    graph = StateGraph(QueryState)
    graph.add_node("authorized_hybrid_retrieval", lambda state: {
        "chunks": retrieve(state["db"], state["user"], state["kb_id"], state["question"])
    })
    graph.add_edge(START, "authorized_hybrid_retrieval")
    graph.add_edge("authorized_hybrid_retrieval", END)
    compiled = graph.compile()
    per_knowledge_base = []
    failed_knowledge_base_ids = []
    for kb_id in kb_ids:
        with _tracer.start_as_current_span("knowledge.retrieval") as span:
            try:
                chunks = compiled.invoke({
                    "db": db, "user": user, "kb_id": kb_id, "question": question,
                })["chunks"]
                per_knowledge_base.append(chunks)
                span.set_attribute("retrieval.chunk_count", len(chunks))
            except Exception as exc:
                db.expunge_all()
                db.rollback()
                logger.warning("Knowledge-base retrieval failed (%s)", type(exc).__name__)
                failed_knowledge_base_ids.append(kb_id)
                span.set_attribute("retrieval.failed", True)

    # Rerank the combined candidates together, then keep the existing eight-source budget.
    candidates = []
    seen_chunk_ids = set()
    for items in per_knowledge_base:
        for chunk in items:
            if chunk.id not in seen_chunk_ids:
                candidates.append(chunk)
                seen_chunk_ids.add(chunk.id)
    if candidates:
        with _tracer.start_as_current_span("knowledge.rerank") as span:
            scores = reranker().predict([(question, chunk.text) for chunk in candidates])
            candidates = [chunk for _, chunk in sorted(zip(scores, candidates), key=lambda item: item[0], reverse=True)[:8]]
            span.set_attribute("retrieval.candidate_count", len(seen_chunk_ids))
            span.set_attribute("retrieval.result_count", len(candidates))
    return {"chunks": candidates, "failed_knowledge_base_ids": failed_knowledge_base_ids}
