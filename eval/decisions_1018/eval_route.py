"""② 質問の振り分け：質問の種類を当てられるかを、モデルごとに測る。

問題：eval/dataset.json の100問(fact・fabrication→one、aggregate→count、semantic→search、ui→ui、
multiturn は道具から)＋第4回の固定5問＋手で書いた12問。
使い方：python eval_route.py [出力名] [モデル…]   → route.json(既定)
2026-10-18 第2版：fabrication の正解を質問の形で付け直し(無い機械の質問は filter、何件は count)、種類の説明に言い方の例を足した。
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from common import APP, TEXT_MODELS, load_env, save, zdr_for

load_env()
from services import decision_client as dc  # noqa: E402
from services import decisions  # noqa: E402

cases = json.loads((APP / "eval" / "dataset.json").read_text())["cases"] if isinstance(
    json.loads((APP / "eval" / "dataset.json").read_text()), dict) else json.loads((APP / "eval" / "dataset.json").read_text())
CAT = {"fact": "one", "fabrication": "one", "aggregate": "count", "semantic": "search", "ui": "ui"}
Q = []
for c in cases:
    if c["category"] == "fabrication":   # 無い番号は「1件」、無い機械・客先などは「絞り込み」、何件は「件数」
        gold = "one" if "KZ25-" in c["question"] else ("count" if "何件" in c["question"] else "filter")
        Q.append((c["id"], c["question"], gold))
    elif c["category"] in CAT:
        Q.append((c["id"], c["question"], CAT[c["category"]]))
    elif c["category"] == "multiturn":
        tools = {t for alt in (c.get("required_tools") or []) for t in alt}
        Q.append((c["id"], c["question"], "ui" if any(t.startswith("ui_") for t in tools) else "one"))
Q += [("s4-Q1", "表面がざらざらして仕上がりが悪い", "search"), ("s4-Q2", "QUICK TURN 250MSY の工具破損", "filter"),
      ("s4-Q3", "GENOS M560-V の寸法不良の傾向と原因は?", "filter"), ("s4-Q4", "バリが取り切れていなかった", "search"),
      ("s4-Q5", "主軸のクランプ圧低下が原因の報告は何件で、どの現象に出ている?", "count")]
Q += [("h-01", "a61nx の2025年9月の報告は？", "filter"), ("h-02", "翠峰重工業向けで未対応の報告書はある？", "filter"),
      ("h-03", "搬送中に隣の品物と当たって付いたキズの事例は？", "search"), ("h-04", "治具の固定が甘くてずれた事例は？", "search"),
      ("h-05", "チャックに切粉が噛み込んで付いた傷の対策は？", "search"), ("h-06", "主軸のクランプ圧低下が原因の報告は何件？", "count"),
      ("h-07", "現象別の件数を多い順に教えて", "count"), ("h-08", "重大度が critical の報告書はどれ？", "filter"),
      ("h-09", "GENOS M560-V の報告はある？", "filter"), ("h-10", "この1年で一番多い現象は？", "count"),
      ("h-11", "このアプリの使い方を教えて", "other"), ("h-12", "フライス加工で起きた穴位置ずれの報告書を見せて", "filter")]


def run(model):
    def one(item):
        qid, q, gold = item
        for attempt in range(2):
            try:
                t0 = time.monotonic()
                res = dc.decide({"質問": q}, {"intent": dc.choice(
                    "`質問` で利用者が求めていることは、どれに一番近いか。" + decisions._GUARD, decisions.INTENTS)},
                    model=model, zdr=zdr_for(model), use_cache=False)
                a = res.answers["intent"]
                return {"id": qid, "q": q, "gold": gold, "pred": a.value, "p": a.p_top, "margin": a.margin,
                        "probs": a.probabilities, "ms": int((time.monotonic() - t0) * 1000), "cost": res.cost_usd}
            except dc.DecisionError as e:
                err = str(e)[:200]
        return {"id": qid, "q": q, "gold": gold, "pred": None, "error": err}

    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(one, Q))


OUTNAME = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".json") else "route.json"
models = [a for a in sys.argv[1:] if not a.endswith(".json")] or TEXT_MODELS
out = {"n": len(Q), "results": {}}
for m in models:
    rs = run(m)
    ok = [r for r in rs if r.get("pred")]
    acc = sum(r["pred"] == r["gold"] for r in ok) / len(rs)
    s4 = [r for r in rs if r["id"].startswith(("s4-", "h-"))]
    acc_s4 = sum(r.get("pred") == r["gold"] for r in s4) / len(s4)
    # 閾値ごとの「採った割合」と「採った中の正解率」
    th = {}
    for t in (0.5, 0.6, 0.7, 0.8, 0.9):
        taken = [r for r in ok if r["p"] >= t]
        th[t] = {"coverage": round(len(taken) / len(rs), 3),
                 "precision": round(sum(r["pred"] == r["gold"] for r in taken) / len(taken), 3) if taken else None}
    summ = {"accuracy": round(acc, 3), "accuracy_s4_hand": round(acc_s4, 3), "errors": len(rs) - len(ok),
            "cost_usd": round(sum(r.get("cost") or 0 for r in ok), 6),
            "median_ms": sorted(r["ms"] for r in ok)[len(ok) // 2] if ok else None, "thresholds": th}
    out["results"][m] = {"summary": summ, "rows": rs}
    print(m, json.dumps(summ, ensure_ascii=False))
    save(OUTNAME, out)
