from urllib.parse import urlparse

from langchain_openai import ChatOpenAI

from server_core.config import settings


def llm_for_request(callbacks=None):
    if not settings.llm_mode or not settings.llm_base_url or not settings.llm_model:
        raise RuntimeError("LLM provider is not configured")
    parsed_url = urlparse(settings.llm_base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname or parsed_url.username or parsed_url.password:
        raise RuntimeError("LLM provider URL is invalid")
    if settings.llm_is_remote and parsed_url.scheme != "https":
        raise RuntimeError("Cloud LLM provider URL must use HTTPS")
    return ChatOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "local",
                      model=settings.llm_model, streaming=True,
                      stream_usage=settings.llm_stream_usage,
                      callbacks=callbacks or [],
                      extra_body={"enable_thinking": False})
