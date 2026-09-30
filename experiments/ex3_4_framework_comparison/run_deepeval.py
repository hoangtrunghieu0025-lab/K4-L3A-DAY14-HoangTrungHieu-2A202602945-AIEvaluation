"""Score the 20 recorded RAG traces with DeepEval. Usage: run_deepeval.py [--limit N]"""
# Needs: pip install deepeval   (tested with deepeval 4.2.7). Use --fill to retry cells that hit transient API errors.
import json
import os
import sys
from pathlib import Path

os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("deepeval_scores.json")

for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

from deepeval.metrics import (  # noqa: E402
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
)
from deepeval.test_case import LLMTestCase  # noqa: E402

gold = {p["id"]: p for p in json.loads((ROOT / "golden_dataset.json").read_text(encoding="utf-8"))["qa_pairs"]}
act = {r["id"]: r for r in json.loads((ROOT / "artifacts" / "actual_answers.json").read_text(encoding="utf-8"))["answers"]}
ids = list(gold)[:limit]

metric_classes = {
    "faithfulness": FaithfulnessMetric,
    "answer_relevancy": AnswerRelevancyMetric,
    "context_recall": ContextualRecallMetric,
    "context_precision": ContextualPrecisionMetric,
}

from concurrent.futures import ThreadPoolExecutor  # noqa: E402


def score_case(i):
    case = LLMTestCase(
        input=gold[i]["question"],
        actual_output=act[i]["actual_answer"],
        expected_output=gold[i]["expected_answer"],
        retrieval_context=[c["text"] for c in act[i]["retrieved_contexts"]],
    )
    out = {}
    for name, cls in metric_classes.items():
        try:
            metric = cls(model=model, include_reason=False, async_mode=False)
            metric.measure(case, _show_indicator=False)
            out[name] = metric.score
        except Exception as exc:  # keep going; record the failure
            out[name] = None
            print(f"{i} {name} FAILED: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
    print(i, {k: (round(v, 3) if v is not None else None) for k, v in out.items()}, flush=True)
    return i, out


if "--fill" in sys.argv:  # retry only the cells that failed with transient API errors
    rows = json.loads(OUT.read_text())["scores"]
    for i in ids:
        todo = [n for n, v in rows[i].items() if v is None]
        if not todo:
            continue
        case = LLMTestCase(
            input=gold[i]["question"],
            actual_output=act[i]["actual_answer"],
            expected_output=gold[i]["expected_answer"],
            retrieval_context=[c["text"] for c in act[i]["retrieved_contexts"]],
        )
        for name in todo:
            try:
                metric = metric_classes[name](model=model, include_reason=False, async_mode=False)
                metric.measure(case, _show_indicator=False)
                rows[i][name] = metric.score
                print(i, name, "->", metric.score, flush=True)
            except Exception as exc:
                print(i, name, "STILL FAILED:", type(exc).__name__, flush=True)
else:
    with ThreadPoolExecutor(max_workers=5) as pool:
        rows = dict(pool.map(score_case, ids))
    rows = {i: rows[i] for i in ids}

OUT.write_text(json.dumps({"model": model, "scores": rows}, indent=2), encoding="utf-8")
print("model:", model, "| samples:", len(rows))
