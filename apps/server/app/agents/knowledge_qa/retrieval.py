import re
from functools import lru_cache

import chromadb
from rank_bm25 import BM25Okapi
from sqlalchemy import select

from server_core.acl import authorized_documents
from server_core.config import settings
from server_core.embeddings import embed_texts
from server_core.model_api import post_model_json
from server_core.models import Chunk


def terms(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]|[a-z0-9]+", text.lower())


@lru_cache(maxsize=1)
def reranker():
    if not settings.reranker_base_url:
        raise RuntimeError("RERANKER_BASE_URL must point to a third-party reranking API")
    if not settings.reranker_api_key:
        raise RuntimeError("RERANKER_API_KEY is required")
    return RemoteReranker()


class RemoteReranker:
    """Adapter for providers exposing a SiliconFlow-compatible /rerank endpoint."""

    def predict(self, pairs):
        if not pairs:
            return []
        queries = {query for query, _document in pairs}
        if len(queries) != 1:
            raise ValueError("Remote reranker expects one query per batch")
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


def retrieve(db, user, kb_id: str, question: str, limit: int = 8) -> list[Chunk]:
    # Resolve ACLs from SQL before either candidate generation path runs.
    documents = authorized_documents(db, user, kb_id)
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

    scores = reranker().predict([(question, row.text) for row in candidates])
    return [row for _, row in sorted(zip(scores, candidates), key=lambda item: item[0], reverse=True)[:limit]]
