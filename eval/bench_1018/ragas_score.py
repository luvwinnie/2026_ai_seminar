"""bench_run.py の記録に RAGAS の指標を付ける(採点役の LLM と埋め込みは研究室の Ollama。トンネル 11435)。

  faithfulness        答えの主張が根拠(contexts)で支えられている割合
  answer_relevancy    答えが質問に答えている度合い(埋め込みで測る)
  factual_correctness 答えが正解(reference)と事実として合っている度合い(正解のある問いだけ)
  context_recall      検索の上位5件が正解の報告書の中身を含む度合い(rag・semantic だけ)
根拠(contexts)= 引用した報告書・事前検索の上位5件・正解の報告書の中身(110件の CSV)＋集計の正解。
使い方(RAGAS 用の別の環境で)：
  tmp/series6/s4/ragas_venv/bin/python ragas_score.py runs/<設定名>.jsonl [--judge gpt-oss:120b] [--limit N]
  → runs/<設定名>.ragas.jsonl
"""
import argparse
import csv
import json
import os
import re
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
APP = HERE.parent.parent
OLLAMA = os.environ.get("OLLAMA_V1", "http://127.0.0.1:11435/v1")
ROWS = {r["defect_id"]: r for r in csv.DictReader(open(APP / "data/defect_reports.csv", encoding="utf-8"))}
CASES = {}
for c in (json.loads((APP / "eval/dataset.json").read_text()).get("cases", []) +
          json.loads((HERE / "ontology_set.json").read_text())["cases"]):
    CASES[c["id"]] = c


def report_text(did):
    r = ROWS.get(did)
    if not r:
        return f"[{did}] この番号の報告書は存在しない"
    return (f"[{did}] 発生日:{r['occurrence_date']} 客先:{r['customer']} 工程:{r['process']} 機械:{r['machine_name']} "
            f"部品:{r['part_name']} 加工数:{r['production_count']} 不適合数:{r['defect_count']} 現象:{r['phenomenon']} "
            f"重大度:{r['severity']} 状態:{r['status']} 損失:{r['total_cost']} 内容:{r['defect_description']} 原因:{r['cause']} 対策:{r['countermeasure']}")


def build(rec):
    case = CASES.get(rec["id"], {})
    gold = case.get("gold_ids") or []
    if rec["category"] == "rag":
        from eval_items import rag_gold
        gold = rag_gold(rec["id"])
    ids = list(dict.fromkeys(gold + (rec.get("cited") or [])[:5] + (rec.get("sources") or [])[:5]))
    ctx = [report_text(i) for i in ids]
    if case.get("stat"):
        ctx.insert(0, f"[集計の正解] {case['stat']}")
    ref = None   # RAGAS は文を主張に分けて比べるので、正解も「質問の答えは…」の文にする
    if case.get("expected"):
        ref = f"「{rec['question']}」の答えは「{'、'.join(case['expected'])}」。"
    elif case.get("expected_any"):
        ref = f"「{rec['question']}」の答えは「{'、'.join(alts[0] for alts in case['expected_any'] if alts)}」。"
    retrieved = [report_text(i) for i in (rec.get("sources") or [])[:5]]
    gold_ref = "\n".join(report_text(i) for i in gold) if gold else None
    return ctx, ref, retrieved, gold_ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--judge", default=os.environ.get("RAGAS_JUDGE", "gpt-oss:120b"))
    ap.add_argument("--emb", default=os.environ.get("RAGAS_EMB", "qwen3-embedding:0.6b"))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.dataset_schema import SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import FactualCorrectness, Faithfulness, LLMContextRecall, ResponseRelevancy
    from ragas.run_config import RunConfig

    llm = LangchainLLMWrapper(ChatOpenAI(base_url=OLLAMA, api_key="ollama", model=a.judge, temperature=0, timeout=600))
    emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(base_url=OLLAMA, api_key="ollama", model=a.emb, check_embedding_ctx_length=False))
    src = Path(a.runs)
    recs = [json.loads(l) for l in src.read_text().splitlines()]
    recs = [r for r in recs if r.get("answer") and r["category"] not in ("ui",)][: a.limit or None]
    out_path = src.with_suffix(".ragas.jsonl")
    done = {json.loads(l)["id"] for l in out_path.read_text().splitlines()} if out_path.exists() else set()
    rc = RunConfig(timeout=900, max_workers=2, max_retries=2)
    with out_path.open("a", encoding="utf-8") as f:
        for r in recs:
            if r["id"] in done:
                continue
            ctx, ref, retrieved, gold_ref = build(r)
            t0 = time.monotonic()
            res = {"id": r["id"], "category": r["category"], "judge": a.judge}
            s = SingleTurnSample(user_input=r["question"], response=r["answer"], retrieved_contexts=ctx, reference=ref)
            metrics = [Faithfulness(), ResponseRelevancy(strictness=1)] + ([FactualCorrectness()] if ref else [])
            try:
                ev = evaluate(EvaluationDataset([s]), metrics=metrics, llm=llm, embeddings=emb, run_config=rc, show_progress=False)
                res.update({k: (None if v != v else v) for k, v in ev.to_pandas().iloc[0].items()
                            if k in ("faithfulness", "answer_relevancy", "factual_correctness(mode=f1)", "factual_correctness")})
            except Exception as e:  # noqa: BLE001
                res["error"] = str(e)[:200]
            if r["category"] in ("rag", "semantic") and gold_ref and retrieved:
                try:
                    s2 = SingleTurnSample(user_input=r["question"], retrieved_contexts=retrieved, reference=gold_ref)
                    ev2 = evaluate(EvaluationDataset([s2]), metrics=[LLMContextRecall()], llm=llm, run_config=rc, show_progress=False)
                    v = ev2.to_pandas().iloc[0].get("context_recall")
                    res["context_recall"] = None if v != v else v
                except Exception as e:  # noqa: BLE001
                    res["error_cr"] = str(e)[:200]
            res["sec"] = round(time.monotonic() - t0, 1)
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            print(json.dumps(res, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
