"""Compare RAGAS vs DeepEval (and the lab's template.py heuristics) on the same 20 traces."""
# Reads ragas_scores.json + deepeval_scores.json (this folder) and artifacts/benchmark_results.json; prints the comparison in exercises.md (Exercise 3.4).
import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
ragas = json.loads((HERE / "ragas_scores.json").read_text())["scores"]
deep = json.loads((HERE / "deepeval_scores.json").read_text())["scores"]
tmpl = {r["id"]: r for r in json.loads((ROOT / "artifacts" / "benchmark_results.json").read_text(encoding="utf-8"))["results"]}
ids = list(tmpl)
assert set(ragas) == set(deep) == set(ids), (len(ragas), len(deep))

R_KEY = {"faithfulness": "faithfulness", "relevance": "answer_relevancy",
         "context_recall": "context_recall", "context_precision": "llm_context_precision_with_reference"}
D_KEY = {"faithfulness": "faithfulness", "relevance": "answer_relevancy",
         "context_recall": "context_recall", "context_precision": "context_precision"}
metrics = list(R_KEY)


def series(src, keymap, m):
    return [src[i].get(keymap[m]) if keymap else src[i][m] for i in ids]


S = {
    "template": {m: [tmpl[i][m] for i in ids] for m in metrics},
    "ragas": {m: series(ragas, R_KEY, m) for m in metrics},
    "deepeval": {m: series(deep, D_KEY, m) for m in metrics},
}
missing = {f: {m: [i for i, v in zip(ids, S[f][m]) if v is None] for m in metrics if any(v is None for v in S[f][m])} for f in S}
print("missing values:", {f: v for f, v in missing.items() if v})


def ranks(v):
    order = sorted(range(len(v)), key=lambda k: v[k])
    r = [0.0] * len(v)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(a, b):
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else float("nan")


def spearman(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    return pearson(ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs]))


def mean(v):
    v = [x for x in v if x is not None]
    return st.mean(v) if v else float("nan")


print("\n== AVERAGES ==  metric: template | ragas | deepeval")
for m in metrics:
    print(f"{m:18s} {mean(S['template'][m]):.3f} | {mean(S['ragas'][m]):.3f} | {mean(S['deepeval'][m]):.3f}")

print("\n== SPEARMAN (rank agreement over 20 cases) ==  ragas~deepeval | ragas~template | deepeval~template")
for m in metrics:
    print(f"{m:18s} {spearman(S['ragas'][m], S['deepeval'][m]):+.2f} | {spearman(S['ragas'][m], S['template'][m]):+.2f} | {spearman(S['deepeval'][m], S['template'][m]):+.2f}")

print("\n== MEAN ABS DIFF ragas vs deepeval ==")
for m in metrics:
    d = [abs(a - b) for a, b in zip(S["ragas"][m], S["deepeval"][m]) if a is not None and b is not None]
    print(f"{m:18s} {st.mean(d):.3f}  (n={len(d)})")

print("\n== #cases below 0.7 / below 0.5 (answer-side metrics) ==")
for f in S:
    for m in ("faithfulness", "relevance"):
        v = [x for x in S[f][m] if x is not None]
        print(f"{f:9s} {m:13s} <0.7: {sum(x < 0.7 for x in v):2d}   <0.5: {sum(x < 0.5 for x in v):2d}   (n={len(v)})")

# per-framework "answer score" = mean(faithfulness, relevance); failure = min(faith, relevance) < 0.7
def flagged(f, thr=0.7):
    out = []
    for k, i in enumerate(ids):
        f_, r_ = S[f]["faithfulness"][k], S[f]["relevance"][k]
        vals = [x for x in (f_, r_) if x is not None]
        if vals and min(vals) < thr:
            out.append(i)
    return out


tmpl_fail = [i for i in ids if not tmpl[i]["passed"]]
print("\n== FLAGGED CASES (min(faithfulness, relevance) < 0.7) ==")
for f in S:
    fl = flagged(f)
    print(f"{f:9s} n={len(fl):2d}: {fl}")
r_fl, d_fl = set(flagged("ragas")), set(flagged("deepeval"))
print("ragas & deepeval overlap:", sorted(r_fl & d_fl), "| Jaccard", round(len(r_fl & d_fl) / max(1, len(r_fl | d_fl)), 2))
print("template.py failures (14):", tmpl_fail)
fp = ["E02", "E05", "M02", "M06", "M07", "A02"]   # content-correct answers the heuristic failed (Cluster 1)
tp = ["H01", "H04", "A03"]                         # answers with a real error (Cluster 3 / A03)
for f in ("ragas", "deepeval"):
    print(f"{f}: on the 6 heuristic false-failures", {i: (S[f]['faithfulness'][ids.index(i)], S[f]['relevance'][ids.index(i)]) for i in fp})
    print(f"{f}: on real-error cases", {i: (S[f]['faithfulness'][ids.index(i)], S[f]['relevance'][ids.index(i)]) for i in tp})

print("\n== bottom-5 by mean(faithfulness, relevance) ==")
for f in S:
    sc = {i: mean([S[f]["faithfulness"][k], S[f]["relevance"][k]]) for k, i in enumerate(ids)}
    print(f"{f:9s}", sorted(sc, key=sc.get)[:5])

print("\n== per-case table ==  id | ragas F,R,Rc,P | deepeval F,R,Rc,P")
for k, i in enumerate(ids):
    fmt = lambda f: ",".join("-" if S[f][m][k] is None else f"{S[f][m][k]:.2f}" for m in ("faithfulness", "relevance", "context_recall", "context_precision"))  # noqa: E731
    print(i, "|", fmt("ragas"), "|", fmt("deepeval"))
