"""Run the synthetic RAG evaluation set against a running API and score with Ragas."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = Path(__file__).with_name("dataset.jsonl")
CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def load_cases(path: Path) -> list[dict]:
    cases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}") from exc
        required = {"id", "question", "reference"}
        if not isinstance(case, dict) or not required.issubset(case):
            raise ValueError(f"Evaluation case at line {line_number} needs id, question, and reference")
        if not all(isinstance(case[key], str) and case[key].strip() for key in required):
            raise ValueError(f"Evaluation case at line {line_number} has an empty required field")
        cases.append(case)
    if not cases:
        raise ValueError("The evaluation dataset contains no cases")
    return cases


def query_chat_api(api_url: str, token: str, knowledge_base_ids: list[str], case: dict) -> dict:
    payload = json.dumps({
        "question": case["question"],
        "knowledge_base_ids": knowledge_base_ids,
    }, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{api_url.rstrip('/')}/chat",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=300) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Chat API returned HTTP {exc.code} for case {case['id']}") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Chat API request failed ({type(exc).__name__}) for case {case['id']}") from None

    answer_parts = []
    sources = []
    for frame in body.replace("\r\n", "\n").split("\n\n"):
        event_name = "message"
        data_lines = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event_name = line.partition(":")[2].strip()
            elif line.startswith("data:"):
                data_lines.append(line.partition(":")[2].lstrip())
        if not data_lines:
            continue
        try:
            event_data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            raise RuntimeError(f"Malformed SSE payload for case {case['id']}") from None
        if event_name == "error":
            raise RuntimeError(f"Chat API emitted an error for case {case['id']}")
        if event_name == "sources":
            sources = event_data.get("sources") or []
        elif event_name == "token":
            answer_parts.append(event_data.get("content", ""))

    answer = "".join(answer_parts).strip()
    if not answer:
        raise RuntimeError(f"Chat API returned no answer for case {case['id']}")
    contexts = [source.get("text", "") for source in sources if source.get("text")]
    citation_numbers = [int(number) for number in CITATION_PATTERN.findall(answer)]
    return {
        "response": answer,
        "retrieved_contexts": contexts,
        "citation_present": bool(citation_numbers),
        "citation_indices_valid": all(1 <= number <= len(sources) for number in citation_numbers),
    }


def build_metrics():
    try:
        from openai import AsyncOpenAI
        from ragas.embeddings.base import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness
    except ImportError as exc:
        raise RuntimeError("Install optional evaluation dependencies with: pip install -r requirements-evaluation.txt") from exc

    base_url = os.environ.get("RAGAS_EVAL_BASE_URL", "").strip()
    api_key = os.environ.get("RAGAS_EVAL_API_KEY", "").strip()
    model = os.environ.get("RAGAS_EVAL_MODEL", "").strip()
    embedding_model = os.environ.get("RAGAS_EVAL_EMBEDDING_MODEL", "").strip()
    if not all((base_url, api_key, model, embedding_model)):
        raise RuntimeError(
            "Set RAGAS_EVAL_BASE_URL, RAGAS_EVAL_API_KEY, RAGAS_EVAL_MODEL, and "
            "RAGAS_EVAL_EMBEDDING_MODEL to an approved OpenAI-compatible evaluation provider"
        )

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    judge_llm = llm_factory(model, provider="openai", client=client)
    judge_embeddings = embedding_factory("openai", model=embedding_model, client=client)
    return {
        "context_precision": ContextPrecision(llm=judge_llm),
        "context_recall": ContextRecall(llm=judge_llm),
        "faithfulness": Faithfulness(llm=judge_llm),
        "answer_relevancy": AnswerRelevancy(llm=judge_llm, embeddings=judge_embeddings),
    }


async def score_case(case: dict, output: dict, metrics: dict) -> dict:
    values = {}
    metric_inputs = {
        "context_precision": {
            "user_input": case["question"], "reference": case["reference"],
            "retrieved_contexts": output["retrieved_contexts"],
        },
        "context_recall": {
            "user_input": case["question"], "reference": case["reference"],
            "retrieved_contexts": output["retrieved_contexts"],
        },
        "faithfulness": {
            "user_input": case["question"], "response": output["response"],
            "retrieved_contexts": output["retrieved_contexts"],
        },
        "answer_relevancy": {
            "user_input": case["question"], "response": output["response"],
        },
    }
    for name, metric in metrics.items():
        if not output["retrieved_contexts"] and name in {
            "context_precision", "context_recall", "faithfulness",
        }:
            # Ragas can return NaN for empty contexts. For this QA eval, no
            # evidence means zero retrieval/grounding quality; keep relevancy
            # separately measurable from the generated response.
            values[name] = 0.0
            continue
        score = await metric.ascore(**metric_inputs[name])
        values[name] = float(score.value)
    return {
        "id": case["id"],
        **values,
        "citation_present": output["citation_present"],
        "citation_indices_valid": output["citation_indices_valid"],
    }


async def run(args: argparse.Namespace) -> Path:
    token = args.token or os.environ.get("RAGAS_API_TOKEN", "")
    if not token:
        raise RuntimeError("Set RAGAS_API_TOKEN or pass --token")
    if not args.knowledge_base_id:
        raise RuntimeError("Pass at least one authorized --knowledge-base-id")

    cases = load_cases(args.dataset)
    metrics = build_metrics()
    records = []
    for case in cases:
        output = await asyncio.to_thread(
            query_chat_api, args.api_url, token, args.knowledge_base_id, case,
        )
        records.append(await score_case(case, output, metrics))

    metric_names = tuple(metrics)
    means = {
        name: sum(record[name] for record in records) / len(records)
        for name in metric_names
    }
    means["citation_presence_rate"] = sum(record["citation_present"] for record in records) / len(records)
    means["citation_index_valid_rate"] = sum(record["citation_indices_valid"] for record in records) / len(records)

    output_path = args.output or ROOT / "evaluation-results" / (
        "ragas-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "ragas_version": __import__("importlib.metadata", fromlist=["version"]).version("ragas"),
        "evaluator_model": os.environ["RAGAS_EVAL_MODEL"],
        "evaluator_embedding_model": os.environ["RAGAS_EVAL_EMBEDDING_MODEL"],
        "case_count": len(records),
        "mean_scores": means,
        "cases": records,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000", help="Base URL of the running API")
    parser.add_argument("--token", help="Bearer token; prefer RAGAS_API_TOKEN environment variable")
    parser.add_argument("--knowledge-base-id", action="append", default=[], help="Authorized KB ID (repeat for multi-KB)")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, help="Report path; defaults to ignored evaluation-results/")
    return parser.parse_args()


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    args = parse_args()
    try:
        output_path = asyncio.run(run(args))
    except Exception as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Ragas evaluation report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
