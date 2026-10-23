import json
from typing import Sequence

from opentelemetry import trace
from server_core.config import settings
from server_core.model_api import post_model_json


_tracer = trace.get_tracer(__name__)


def _record_embedding_usage(span, response: dict, input_count: int) -> None:
    span.set_attribute("embedding.input_count", input_count)
    span.set_attribute("langfuse.observation.model.name", settings.embedding_model)
    usage = response.get("usage")
    if not isinstance(usage, dict):
        span.set_attribute("embedding.usage_reported", False)
        return
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    total_tokens = usage.get("total_tokens", input_tokens)
    if isinstance(input_tokens, (int, float)):
        span.set_attribute("embedding.input_tokens", int(input_tokens))
        span.set_attribute("embedding.usage_reported", True)
        span.set_attribute("langfuse.observation.usage_details", json.dumps({
            "input": int(input_tokens),
        }))
        price = settings.embedding_price_per_1m
        if price is not None:
            span.set_attribute("langfuse.observation.cost_details", json.dumps({
                "input": int(input_tokens) * price / 1_000_000,
                "total": int(input_tokens) * price / 1_000_000,
                "currency": "USD",
            }))
    else:
        span.set_attribute("embedding.usage_reported", False)
    if isinstance(total_tokens, (int, float)):
        span.set_attribute("embedding.total_tokens", int(total_tokens))


def _remote_embeddings(texts: Sequence[str]) -> list[list[float]]:
    if not settings.embedding_api_key:
        raise RuntimeError("EMBEDDING_API_KEY is required")

    vectors: list[list[float]] = []
    # Keep requests bounded so larger Markdown documents fit provider limits.
    for offset in range(0, len(texts), 32):
        batch = list(texts[offset:offset + 32])
        with _tracer.start_as_current_span("knowledge.embedding") as span:
            response = post_model_json(
                settings.embedding_base_url,
                "/embeddings",
                settings.embedding_api_key,
                {"model": settings.embedding_model, "input": batch},
            )
            _record_embedding_usage(span, response, len(batch))
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
