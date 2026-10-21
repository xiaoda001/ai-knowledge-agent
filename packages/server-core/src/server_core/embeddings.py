from typing import Sequence

from server_core.config import settings
from server_core.model_api import post_model_json


def _remote_embeddings(texts: Sequence[str]) -> list[list[float]]:
    if not settings.embedding_api_key:
        raise RuntimeError("EMBEDDING_API_KEY is required")

    vectors: list[list[float]] = []
    # Keep requests bounded so larger Markdown documents fit provider limits.
    for offset in range(0, len(texts), 32):
        batch = list(texts[offset:offset + 32])
        response = post_model_json(
            settings.embedding_base_url,
            "/embeddings",
            settings.embedding_api_key,
            {"model": settings.embedding_model, "input": batch},
        )
        items = response.get("data")
        if not isinstance(items, list) or len(items) != len(batch):
            raise RuntimeError("Embedding API returned an unexpected number of vectors")
        ordered = sorted(items, key=lambda item: item.get("index", 0))
        vectors.extend([[float(value) for value in item["embedding"]] for item in ordered])
    return vectors


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embed text through the configured third-party embeddings API."""
    if not texts:
        return []
    if not settings.embedding_base_url:
        raise RuntimeError("EMBEDDING_BASE_URL must point to a third-party embeddings API")
    return _remote_embeddings(texts)
