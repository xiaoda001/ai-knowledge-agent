from collections.abc import Mapping

from langchain_core.callbacks import BaseCallbackHandler

from app.services.chat_context import token_count
from server_core.config import settings


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content or "")


def _usage_pair(usage) -> tuple[int, int] | None:
    if not isinstance(usage, Mapping):
        return None
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    if not isinstance(input_tokens, (int, float)) or not isinstance(output_tokens, (int, float)):
        return None
    return max(0, int(input_tokens)), max(0, int(output_tokens))


class ChatUsageTracker(BaseCallbackHandler):
    """Accumulate provider usage, falling back to local token estimates per model call."""

    raise_error = False

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.estimated = False
        self._prompt_estimates = {}
        self._recorded_runs = set()

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        prompt_tokens = 0
        for batch in messages:
            for message in batch:
                role = getattr(message, "type", message.__class__.__name__)
                content = _content_text(getattr(message, "content", ""))
                prompt_tokens += token_count(f"{role}: {content}") + 4
        self._prompt_estimates[run_id] = prompt_tokens

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        self._prompt_estimates[run_id] = sum(token_count(prompt) + 4 for prompt in prompts)

    def on_llm_end(self, response, *, run_id, **kwargs):
        if run_id in self._recorded_runs:
            return
        self._recorded_runs.add(run_id)

        actual = _usage_pair((getattr(response, "llm_output", None) or {}).get("token_usage"))
        generations = getattr(response, "generations", []) or []
        if actual is None:
            for batch in generations:
                for generation in batch:
                    message = getattr(generation, "message", None)
                    actual = _usage_pair(getattr(message, "usage_metadata", None))
                    if actual is not None:
                        break
                if actual is not None:
                    break

        if actual is not None:
            self.input_tokens += actual[0]
            self.output_tokens += actual[1]
            return

        self.estimated = True
        self.input_tokens += self._prompt_estimates.get(run_id, 0)
        output_text = []
        for batch in generations:
            for generation in batch:
                message = getattr(generation, "message", None)
                content = getattr(message, "content", None) if message is not None else None
                output_text.append(_content_text(content if content is not None else getattr(generation, "text", "")))
        self.output_tokens += token_count("".join(output_text))

    def snapshot(self) -> dict:
        total_tokens = self.input_tokens + self.output_tokens
        input_rate = getattr(settings, "llm_input_price_per_1m", None)
        output_rate = getattr(settings, "llm_output_price_per_1m", None)
        pricing_configured = input_rate is not None and output_rate is not None
        cost = None
        if pricing_configured:
            cost = round((self.input_tokens * input_rate + self.output_tokens * output_rate) / 1_000_000, 8)
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": total_tokens,
            "tokens_estimated": self.estimated,
            "cost_usd": cost,
            "pricing_configured": pricing_configured,
        }
