"""Score the 20 recorded RAG traces with RAGAS. Usage: run_ragas.py [--limit N]"""
# Needs its own venv: pip install ragas "langchain-community<0.4"   (ragas 0.4.3 fails to import with newer langchain-community)
import json
import os
import sys
from pathlib import Path

os.environ["RAGAS_DO_NOT_TRACK"] = "true"
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("ragas_scores.json")

# load OPENAI_API_KEY from the project's .env without printing it
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # noqa: E402
from ragas import EvaluationDataset, evaluate  # noqa: E402
from ragas.dataset_schema import SingleTurnSample  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import (  # noqa: E402
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
    ResponseRelevancy,
)

gold = {p["id"]: p for p in json.loads((ROOT / "golden_dataset.json").read_text(encoding="utf-8"))["qa_pairs"]}
act = {r["id"]: r for r in json.loads((ROOT / "artifacts" / "actual_answers.json").read_text(encoding="utf-8"))["answers"]}
ids = list(gold)[:limit]

samples = [
    SingleTurnSample(
        user_input=gold[i]["question"],
        response=act[i]["actual_answer"],
        retrieved_contexts=[c["text"] for c in act[i]["retrieved_contexts"]],
        reference=gold[i]["expected_answer"],
    )
    for i in ids
]
model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
llm = LangchainLLMWrapper(ChatOpenAI(model=model, temperature=0))
emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model="text-embedding-3-small"))

result = evaluate(
    EvaluationDataset(samples=samples),
    metrics=[Faithfulness(), ResponseRelevancy(), LLMContextRecall(), LLMContextPrecisionWithReference()],
    llm=llm,
    embeddings=emb,
    raise_exceptions=False,
    show_progress=False,
)
rows = {i: {k: (None if v != v else v) for k, v in score.items()} for i, score in zip(ids, result.scores)}
OUT.write_text(json.dumps({"model": model, "scores": rows}, indent=2), encoding="utf-8")
print("model:", model, "| samples:", len(rows))
for i, s in rows.items():
    print(i, {k: (round(v, 3) if v is not None else None) for k, v in s.items()})
