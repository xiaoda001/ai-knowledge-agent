"""Small JSON client for configurable OpenAI-style model provider endpoints."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


def post_model_json(base_url: str, endpoint: str, api_key: str, payload: dict) -> dict:
    """POST JSON to a provider endpoint, appending its path to a configured base URL."""
    parsed = urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise RuntimeError("Model API base URL must be an HTTP(S) origin/path without credentials or query")

    path = parsed.path.rstrip("/")
    endpoint = endpoint.rstrip("/")
    if not path.endswith(endpoint):
        path += endpoint
    url = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Do not echo provider response bodies; they can contain submitted text.
        raise RuntimeError(f"Model API request failed with HTTP {exc.code}") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Model API request failed ({type(exc).__name__})") from None
    if not isinstance(result, dict):
        raise RuntimeError("Model API returned a non-object response")
    return result
