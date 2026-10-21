import os
import math
from sqlalchemy.engine import URL
from dotenv import load_dotenv
from urllib.parse import urlsplit


# Load the repository .env for local runs. Existing process/Compose environment
# variables take precedence, so deployments can still inject secrets safely.
load_dotenv(override=False)


def _boolean_setting(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "true" if default else "false").strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be set to true or false")
    return value == "true"


def _optional_token_price(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative USD price per 1M tokens") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a non-negative USD price per 1M tokens")
    return value


class Settings:
    database_url = os.getenv("DATABASE_URL") or URL.create(
        "mysql+pymysql",
        username=os.getenv("MYSQL_USER", "kb"),
        password=os.getenv("MYSQL_PASSWORD", "kb"),
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE", "knowledge"),
    )
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    chroma_host = os.getenv("CHROMA_HOST", "chroma")
    chroma_port = int(os.getenv("CHROMA_PORT", "8000"))
    embedding_model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    embedding_base_url = os.getenv("EMBEDDING_BASE_URL", "").strip()
    embedding_api_key = os.getenv("EMBEDDING_API_KEY", "")
    reranker_model = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    reranker_base_url = os.getenv("RERANKER_BASE_URL", "").strip()
    reranker_api_key = os.getenv("RERANKER_API_KEY", "")
    jwt_secret = os.getenv("JWT_SECRET", "")
    jwt_minutes = int(os.getenv("JWT_MINUTES", "1440"))
    cors_origins = tuple(origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip())
    upload_dir = os.getenv("UPLOAD_DIR", "/data/uploads")
    llm_mode = _boolean_setting("LLM_MODE")
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    llm_api_key = os.getenv("LLM_API_KEY", "")
    llm_model = os.getenv("LLM_MODEL", "")
    llm_stream_usage = _boolean_setting("LLM_STREAM_USAGE")
    llm_input_price_per_1m = _optional_token_price("LLM_INPUT_PRICE_PER_1M")
    llm_output_price_per_1m = _optional_token_price("LLM_OUTPUT_PRICE_PER_1M")
    redaction_rules = os.getenv("REDACTION_RULES", "")
    memory_history_token_budget = max(256, int(os.getenv("MEMORY_HISTORY_TOKEN_BUDGET", "6000")))
    memory_summary_token_budget = max(128, int(os.getenv("MEMORY_SUMMARY_TOKEN_BUDGET", "1200")))
    memory_summary_output_tokens = max(128, int(os.getenv("MEMORY_SUMMARY_OUTPUT_TOKENS", "1500")))
    memory_workspace_token_budget = max(128, int(os.getenv("MEMORY_WORKSPACE_TOKEN_BUDGET", "1200")))

    @property
    def llm_is_remote(self) -> bool:
        hostname = urlsplit(self.llm_base_url).hostname
        return bool(hostname and hostname.lower() not in {
            "localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama",
        })


settings = Settings()
