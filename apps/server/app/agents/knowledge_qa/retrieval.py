import json
import re
from functools import lru_cache

import chromadb
from opentelemetry import trace
from rank_bm25 import BM25Okapi
from sqlalchemy import select

from server_core.acl import authorized_documents
from server_core.config import settings
from server_core.document_versions import document_version_states
from server_core.embeddings import embed_texts
from server_core.model_api import post_model_json
from server_core.models import Chunk, Document


_tracer = trace.get_tracer(__name__)


def terms(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]|[a-z0-9]+", text.lower())


@lru_cache(maxsize=1)
def reranker():
    if not settings.reranker_base_url:
        raise RuntimeError("RERANKER_BASE_URL must point to a third-party reranking API")
    if not settings.reranker_api_key:
        raise RuntimeError("RERANKER_API_KEY is required")
    return RemoteReranker()


def rerank_document_text(chunk, document, version_status: str | None = None) -> str:
    """Give the reranker concise provenance and version context with each chunk."""
    if document is None:
        return chunk.text
    status_labels = {
        "current": "当前版本",
        "scheduled": "待生效版本",
        "needs_review": "版本日期待确认",
        "superseded": "已被新版替代",
        "expired": "已过期",
    }
    metadata = [f"文件名：{document.filename or '未知'}"]
    if document.publication_date:
        metadata.append(f"发布日期：{document.publication_date.isoformat()}")
    if document.effective_date:
        metadata.append(f"生效日期：{document.effective_date.isoformat()}")
    if version_status:
        metadata.append(f"版本状态：{status_labels.get(version_status, version_status)}")
    return f"{'；'.join(metadata)}\n正文片段：{chunk.text}"


class RemoteReranker:
    """Adapter for providers exposing a SiliconFlow-compatible /rerank endpoint."""

    def predict(self, pairs):
        if not pairs:
            return []
        queries = {query for query, _document in pairs}
        if len(queries) != 1:
            raise ValueError("Remote reranker expects one query per batch")
        with _tracer.start_as_current_span("knowledge.rerank.request") as span:
            span.set_attribute("langfuse.observation.model.name", settings.reranker_model)
            span.set_attribute("rerank.document_count", len(pairs))
            response = post_model_json(
                settings.reranker_base_url,
                "/rerank",
                settings.reranker_api_key,
                {
                    "model": settings.reranker_model,
                    "query": pairs[0][0],
                    "documents": [document for _query, document in pairs],
                    "top_n": len(pairs),
                    "return_documents": False,
                },
            )
            meta = response.get("meta") or {}
            billed_units = meta.get("billed_units") or {}
            usage = meta.get("tokens") or response.get("usage") or {}
            if isinstance(billed_units, dict):
                span.set_attribute("rerank.billed_units", json.dumps(billed_units))
            input_tokens = (billed_units.get("input_tokens") if isinstance(billed_units, dict) else None)
            if not isinstance(input_tokens, (int, float)):
                input_tokens = usage.get("input_tokens", usage.get("prompt_tokens")) if isinstance(usage, dict) else None
            output_tokens = (billed_units.get("output_tokens") if isinstance(billed_units, dict) else None)
            if not isinstance(output_tokens, (int, float)):
                output_tokens = usage.get("output_tokens", usage.get("completion_tokens")) if isinstance(usage, dict) else None
            if isinstance(input_tokens, (int, float)):
                span.set_attribute("rerank.input_tokens", int(input_tokens))
                span.set_attribute("rerank.usage_reported", True)
                usage_details = {"input": int(input_tokens)}
                if isinstance(output_tokens, (int, float)):
                    usage_details["output"] = int(output_tokens)
                span.set_attribute("langfuse.observation.usage_details", json.dumps(usage_details))
                price = settings.reranker_price_per_1m
                if price is not None:
                    cost = int(input_tokens) * price / 1_000_000
                    span.set_attribute("langfuse.observation.cost_details", json.dumps({
                        "input": cost, "total": cost, "currency": "USD",
                    }))
            else:
                span.set_attribute("rerank.usage_reported", False)
        results = response.get("results")
        if not isinstance(results, list):
            raise RuntimeError("Reranker API returned an unexpected response")
        scores = [float("-inf")] * len(pairs)
        for item in results:
            index = item.get("index")
            score = item.get("relevance_score")
            if isinstance(index, int) and 0 <= index < len(scores) and score is not None:
                scores[index] = float(score)
        if any(score == float("-inf") for score in scores):
            raise RuntimeError("Reranker API response omitted one or more document scores")
        return scores


def retrieve(db, user, kb_id: str, question: str, limit: int = 8,
             include_history: bool = False) -> list[Chunk]:
    # Resolve ACLs from SQL before either candidate generation path runs.
    documents = authorized_documents(db, user, kb_id, include_history=include_history)
    document_ids = [document.id for document in documents]
    if not document_ids:
        return []

    rows = db.scalars(select(Chunk).where(Chunk.document_id.in_(document_ids))).all()
    if not rows:
        return []

    bm25 = BM25Okapi([terms(row.text) for row in rows])
    bm25_scores = bm25.get_scores(terms(question))
    lexical = [rows[index] for index in sorted(range(len(rows)), key=lambda index: bm25_scores[index], reverse=True)[:30]]

    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    collection = client.get_collection("knowledge_chunks")
    dense = collection.query(
        query_embeddings=embed_texts([question]), n_results=min(30, len(rows)),
        where={"document_id": {"$in": document_ids}},
    )

    # Intersect vector results with the SQL-authorized corpus as a second boundary.
    by_id = {row.id: row for row in rows}
    ranks: dict[str, float] = {}
    for rank, row in enumerate(lexical, 1):
        ranks[row.id] = ranks.get(row.id, 0) + 1 / (60 + rank)
    for rank, chunk_id in enumerate(dense.get("ids", [[]])[0], 1):
        if chunk_id in by_id:
            ranks[chunk_id] = ranks.get(chunk_id, 0) + 1 / (60 + rank)
    candidates = [by_id[key] for key in sorted(ranks, key=ranks.get, reverse=True)[:30]]
    if not candidates:
        return []

    version_documents = db.scalars(select(Document).where(Document.knowledge_base_id == kb_id)).all()
    version_states = document_version_states(version_documents)
    document_by_id = {document.id: document for document in version_documents}
    scores = reranker().predict([
        (question, rerank_document_text(row, document_by_id.get(row.document_id),
                                        version_states.get(row.document_id)))
        for row in candidates
    ])
    return [row for _, row in sorted(zip(scores, candidates), key=lambda item: item[0], reverse=True)[:limit]]
