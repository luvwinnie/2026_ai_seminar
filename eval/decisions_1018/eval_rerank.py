"""① 検索の並べ替え：例アプリの検索(BM25＋e5→RRF、SudachiPy あり)の上位30件を、判断モデルで並べ直すと
上位5件の正解がどれだけ増えるかを、モデルごとに測る。

前提：S4_WORK に 110件の DB と Chroma(tmp/series6/s4/measure/measure_fixed5.py が作ったもの)。
使い方：S4_WORK=… PYTHONPATH=<sudachi> python eval_rerank.py [モデル…]   → rerank.json
"""
import os
import sys
import time
from pathlib import Path

from common import load_env, save

load_env()
S = Path(os.environ["S4_WORK"])
os.environ["DB_PATH"] = str(S / "exp.db")
os.environ["CHROMA_PATH"] = str(S / "chroma")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from database import SessionLocal  # noqa: E402
from models import DefectReport  # noqa: E402
from services import decision_client as dc  # noqa: E402
from services import decisions, hybrid, rag  # noqa: E402

db = SessionLocal()
rows = {r.defect_id: r for r in db.query(DefectReport).all()}
by = lambda f: {i for i, r in rows.items() if f(r)}
PH = lambda name: by(lambda r: r.phenomenon == name)
QUERIES = [
    ("Q1", "表面がざらざらして仕上がりが悪い", PH("面粗さ不良")),
    ("Q2", "QUICK TURN 250MSY の工具破損", {"KZ25-0039"}),
    ("Q3", "GENOS M560-V の寸法不良の傾向と原因は?", set()),
    ("Q4", "バリが取り切れていなかった", PH("バリ残り")),
    ("Q5", "主軸のクランプ圧低下が原因の報告は何件で、どの現象に出ている?", by(lambda r: "クランプ圧" in (r.cause or ""))),
    ("P1", "ドリルやエンドミルが折れた", PH("工具破損")),
    ("P2", "部品が曲がって反ってしまった", PH("ひずみ変形")),
    ("P3", "穴の位置が図面と合わない", PH("穴位置ずれ")),
    ("P4", "加工面に段がついてしまった", PH("加工段差")),
    ("P5", "加工プログラムの設定を間違えた", PH("NCプログラム誤り")),
    ("P6", "寸法が公差から外れていた", PH("寸法公差外れ")),
    ("P7", "刻印の番号が間違っていた", PH("刻印・表示誤り")),
    ("P8", "部品を逆向きに取り付けた", PH("取付方向誤り")),
    ("N1", "搬送中に隣の品物と当たって付いたキズ", by(lambda r: "隣接品" in (r.defect_description or ""))),
    ("N2", "治具の固定が甘くてずれた事例は？", by(lambda r: "クランプ圧" in (r.cause or ""))),
    ("N3", "チャックに切粉が噛み込んで付いた傷の対策は？", by(lambda r: "切粉" in (r.defect_description or "") and "噛み込" in (r.defect_description or ""))),
]
N_CAND = 30

cands = {}
for qid, q, gold in QUERIES:
    items = hybrid.fuse(db, q, rag._dense_search(q), top_k=N_CAND)
    cands[qid] = items


def metrics(ids, gold):
    top = ids[:5]
    hit = sum(i in gold for i in top)
    first = next((k + 1 for k, i in enumerate(ids) if i in gold), None)
    return {"p5": hit / 5, "recall5": (hit / min(5, len(gold))) if gold else None, "first": first, "top5": top}


models = sys.argv[1:] or ["typesafe/jev-1.14", "typesafe/jev-1.13", "perplexity/pplx-decider-flash-v1.2", "perplexity/pplx-decider-v1.2",
                          "microsoft/microsoft-decision-1", "liquid/d1-ultra", "inception/mercury-decide"]
out = {"n_candidates": N_CAND, "queries": {qid: {"q": q, "gold": sorted(g), "pool_hits": sum(it["defect_id"] in g for it in cands[qid]),
                                                 "before": metrics([it["defect_id"] for it in cands[qid]], g)} for qid, q, g in QUERIES},
       "models": {}}
for m in models:
    t0 = time.monotonic()
    per, cost = {}, 0.0
    for qid, q, gold in QUERIES:
        try:
            ranked, info = decisions.rerank(q, cands[qid], rows, top_k=N_CAND, model=m)
        except dc.DecisionError as e:
            per[qid] = {"error": str(e)[:200]}
            continue
        ids = [it["defect_id"] for it in ranked]
        per[qid] = dict(metrics(ids, gold), max_rel=info["max_relevance"], abstain=info["abstain"],
                        rel_top5=[it["relevance"] for it in ranked[:5]])
        cost += info["cost_usd"]
    ok = [v for k, v in per.items() if "p5" in v and QUERIES[[x[0] for x in QUERIES].index(k)][2]]
    summ = {"mean_p5": round(sum(v["p5"] for v in ok) / len(ok), 3),
            "mean_recall5": round(sum(v["recall5"] for v in ok) / len(ok), 3),
            "q3_abstain": per.get("Q3", {}).get("abstain"), "q3_max_rel": per.get("Q3", {}).get("max_rel"),
            "cost_usd": round(cost, 5), "sec": round(time.monotonic() - t0, 1)}
    out["models"][m] = {"summary": summ, "per_query": per}
    print(m, summ, {k: v.get("p5") for k, v in per.items()})
    save("rerank.json", out)
base = [v["before"] for k, v in out["queries"].items() if v["gold"]]
print("before mean_p5", round(sum(b["p5"] for b in base) / len(base), 3),
      "mean_recall5", round(sum(b["recall5"] for b in base) / len(base), 3),
      {k: v["before"]["p5"] for k, v in out["queries"].items()}, "pool", {k: v["pool_hits"] for k, v in out["queries"].items()})
