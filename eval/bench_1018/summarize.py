"""runs/*.jsonl(チャット)と runs/*.ragas.jsonl(RAGAS)をまとめて、bench_summary.json と bench_report.md を作る。"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LLM_NAME = {"gemma4_26b": "gemma4:26b", "gpt-oss_20b": "gpt-oss:20b", "qwen3.6_35b-a3b": "qwen3.6:35b-a3b",
            "ds4_deepseek-v4-flash": "DeepSeek V4 Flash", "qwen3.8_27b": "qwen3.8:27b", "qwen3.5_9b": "qwen3.5:9b"}


def mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(statistics.mean(xs), 4) if xs else None


def rate(xs):
    xs = [bool(x) for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def pctl(xs, q):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else None


# 採点し直す(bench_run.score の今の版で。記録した答え・道具・候補から計算し直す)
import csv
import sys
sys.path.insert(0, str(HERE))
from bench_run import load_cases, score  # noqa: E402
_rows = list(csv.DictReader(open(HERE.parent.parent / "data/defect_reports.csv", encoding="utf-8")))
VALID = {r["defect_id"] for r in _rows}
CUST = sorted({r["customer"] for r in _rows})
CASE = {c["id"]: c for c in load_cases()}


def rescore(r):
    c = CASE.get(r["id"])
    if not c:
        return r
    out = {k: r.get(k) for k in ("answer", "tools", "sources", "citations", "route")}
    out["answer"] = out["answer"] or ""
    out["tools"] = out["tools"] or []
    out["sources"] = out["sources"] or []
    r.update(score(c, out, VALID, CUST))
    return r


configs = []
for f in sorted(HERE.glob("runs/*_dec-*.jsonl")):
    if f.name.endswith(".ragas.jsonl"):
        continue
    name = f.stem
    llm, dec = name.rsplit("_dec-", 1)
    recs = [rescore(json.loads(l)) for l in f.read_text().splitlines()]
    rg = {}
    rf = f.with_suffix(".ragas.jsonl")
    if rf.exists():
        rg = {json.loads(l)["id"]: json.loads(l) for l in rf.read_text().splitlines()}
    by = defaultdict(list)
    for r in recs:
        by[r["category"]].append(r)
    ont = by.get("ontology", [])
    c = {"config": name, "llm": LLM_NAME.get(llm, llm), "decisions": dec, "n": len(recs),
         "accuracy": rate(r.get("correct") for r in recs), "tool_ok": rate(r.get("tool_ok") for r in recs),
         "citation_valid": rate(r.get("citation_valid") for r in recs),
         "false_claims": sum(1 for r in recs if r.get("false_claim")),
         "hallucinated_ids": sum(len(r.get("hallucinated_ids") or []) for r in recs),
         "errors": sum(1 for r in recs if r.get("error")),
         "median_total_s": pctl([r.get("total_s") for r in recs], 0.5), "p95_total_s": pctl([r.get("total_s") for r in recs], 0.95),
         "median_sources_s": pctl([(r.get("times") or {}).get("sources") for r in recs], 0.5),
         "median_first_token_s": pctl([(r.get("times") or {}).get("token") for r in recs], 0.5),
         "by_category": {k: rate(r.get("correct") for r in v) for k, v in sorted(by.items())},
         "ontology": {"accuracy": rate(r.get("correct") for r in ont),
                      "count_rate": rate(r.get("correct") for r in ont if not r["id"].startswith("ont-none")),
                      "no_substitution": rate(r.get("correct") for r in ont if r["id"].startswith("ont-none"))},
         "rag_recall5_sources": mean([r.get("recall5_sources") for r in by.get("rag", [])]),
         "cite_unsupported": sum(r.get("cite_unsupported") or 0 for r in recs),
         "route_taken": rate(r.get("route_taken") for r in recs if r.get("route_intent")),
         "faithfulness": mean([v.get("faithfulness") for v in rg.values()]),
         "answer_relevancy": mean([v.get("answer_relevancy") for v in rg.values()]),
         "factual_correctness": mean([v.get("factual_correctness(mode=f1)", v.get("factual_correctness")) for v in rg.values()]),
         "context_recall": mean([v.get("context_recall") for v in rg.values()]),
         "ragas_n": len(rg)}
    configs.append(c)
out = {"configs": configs, "notes": ""}
(HERE / "bench_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
L = ["# チャットの全問ベンチマーク(2026-10-18)\n",
     "例アプリ(Docker)・チャットの LLM は研究室のサーバ(Ollama と DeepSeek V4 Flash)・判断モデルは inception/mercury-decide:free(ZDR なし・架空データだけ)。"
     "問題は137問(問題集100・Ontology 21・検索16)。RAGAS 0.4.3(採点役 gpt-oss:120b、埋め込み qwen3-embedding:0.6b)。\n",
     "| LLM | 判断モデル | 問 | 正解率 | 道具 | 番号を作らない | 虚偽の操作 | faithfulness | relevancy | factual | context recall | 1問(中央値/95%) | 候補が届く |",
     "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
f2 = lambda x: "—" if x is None else f"{x:.2f}"
p = lambda x: "—" if x is None else f"{x:.1%}"
for c in configs:
    L.append(f"| {c['llm']} | {c['decisions']} | {c['n']} | {p(c['accuracy'])} | {p(c['tool_ok'])} | {p(c['citation_valid'])} | {c['false_claims']} | "
             f"{f2(c['faithfulness'])} | {f2(c['answer_relevancy'])} | {f2(c['factual_correctness'])} | {f2(c['context_recall'])} | "
             f"{c['median_total_s']}／{c['p95_total_s']} 秒 | {c['median_sources_s']} 秒 |")
L.append("\n## カテゴリごとの正解率\n")
cats = sorted({k for c in configs for k in c["by_category"]})
L.append("| LLM | 判断モデル | " + " | ".join(cats) + " |")
L.append("|---|---|" + "---|" * len(cats))
for c in configs:
    L.append(f"| {c['llm']} | {c['decisions']} | " + " | ".join(p(c["by_category"].get(k)) for k in cats) + " |")
(HERE / "bench_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
