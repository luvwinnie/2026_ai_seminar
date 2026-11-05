"""② 質問の振り分けの問題(eval_route.py 第2版と同じ117問)。"""
import json

from common import APP


def items():
    raw = json.loads((APP / "eval" / "dataset.json").read_text())
    cases = raw["cases"] if isinstance(raw, dict) else raw
    CAT = {"fact": "one", "aggregate": "count", "semantic": "search", "ui": "ui"}
    Q = []
    for c in cases:
        if c["category"] == "fabrication":
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
    return Q
