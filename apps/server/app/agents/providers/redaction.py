import json
import re

from server_core.config import settings


def redact(text: str) -> str:
    if not settings.llm_mode or not settings.llm_is_remote:
        return text
    if not settings.redaction_rules.strip():
        return text
    try:
        rules = json.loads(settings.redaction_rules)
        if not isinstance(rules, list) or not rules:
            raise ValueError("empty policy")
        for rule in rules:
            text = re.sub(rule["pattern"], rule.get("replacement", "[REDACTED]"), text)
        return text
    except Exception as exc:
        raise RuntimeError("Redaction policy failed; outbound request denied") from exc
