# -*- coding: utf-8 -*-
"""評価データセット生成 — 架空データ(defect_reports.csv)を Ground Truth に、
チャットAIの回答品質(事実・集計・意味検索・幻覚耐性)を測る質問を決定論的に作る。

実行: ../.venv/bin/python make_dataset.py  → dataset.json
乱数 seed=0 固定。データを再生成したら本スクリプトも再実行すること。
"""
import csv
import json
import random
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
CSV = HERE.parent / "data" / "defect_reports.csv"

rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
rng = random.Random(0)
ids = {r["defect_id"] for r in rows}

cases = []

AGG_TOOLS = ["get_statistics", "list_defect_reports"]


def add(cat, question, **kw):
    cases.append({"id": f"{cat}-{sum(c['category'] == cat for c in cases) + 1:02d}",
                  "category": cat, "question": question, **kw})

# ---------- 1) 事実参照(単票の項目) ----------
DATA_TOOLS = ["get_defect_report", "list_defect_reports", "search_defect_reports"]
_FACT_FIELDS = [
    ("使用機械はどれですか?", "machine_name", 6),
    ("客先はどこですか?", "customer", 5),
    ("現象分類は何ですか?", "phenomenon", 5),
    ("発生工程はどこですか?", "process", 4),
    ("作業者は誰ですか?", "operator_name", 4),
    ("部品名は何ですか?", "part_name", 3),
    ("発生日はいつですか?", "occurrence_date", 3),
]
for q, field, n in _FACT_FIELDS:
    for r in rng.sample(rows, n):
        add("fact", f"{r['defect_id']}の{q}", expected=[r[field]], gold_ids=[r["defect_id"]],
            required_tools=[DATA_TOOLS])

# ---------- 2) 集計 ----------
mc = Counter(r["machine_name"] for r in rows)
for m, n in rng.sample(sorted(mc.items()), 6):
    add("aggregate", f"{m}の報告書は全部で何件ありますか?", expected=[str(n)], stat=f"{m}の件数={n}",
        required_tools=[AGG_TOOLS])
pc = Counter(r["phenomenon"] for r in rows)
for ph, n in rng.sample(sorted(pc.items())[:8], 4):
    add("aggregate", f"現象分類が{ph}の報告書は何件ありますか?", expected=[str(n)], stat=f"{ph}の件数={n}",
        required_tools=[AGG_TOOLS])
# 月別(3ヶ月ぶん)
for month, label in (("2025-10", "2025年10月"), ("2025-07", "2025年7月"), ("2026-02", "2026年2月")):
    n = sum(1 for r in rows if r["occurrence_date"].startswith(month))
    add("aggregate", f"{label}に発生した報告書は何件ですか?", expected=[str(n)], stat=f"{month}の件数={n}",
        required_tools=[AGG_TOOLS])
# 客先別件数
cc = Counter(r["customer"] for r in rows)
for c, n in rng.sample(sorted(cc.items()), 3):
    add("aggregate", f"{c}向けの報告書は何件ありますか?", expected=[str(n)], stat=f"{c}の件数={n}",
        required_tools=[AGG_TOOLS])
# 重大度・状態
n_crit = sum(1 for r in rows if r["severity"] == "critical")
add("aggregate", "重大度がcriticalの報告書は何件ですか?", expected=[str(n_crit)], stat=f"critical={n_crit}",
    required_tools=[AGG_TOOLS])
n_open = sum(1 for r in rows if r["status"] == "open")
add("aggregate", "状態が未対応(open)の報告書は何件ですか?", expected=[str(n_open)], stat=f"open={n_open}",
    required_tools=[AGG_TOOLS])
# 総件数
add("aggregate", "報告書は全部で何件登録されていますか?", expected=[str(len(rows))], stat=f"総件数={len(rows)}",
    required_tools=[AGG_TOOLS])
# 工程別件数
prc = Counter(r["process"] for r in rows)
for pr, n in rng.sample(sorted(prc.items()), 1):
    add("aggregate", f"工程が{pr}の報告書は何件ありますか?", expected=[str(n)], stat=f"{pr}の件数={n}",
        required_tools=[AGG_TOOLS])
# 最多機械(一意な最大のときのみ)
top2 = mc.most_common(2)
if len(top2) == 1 or top2[0][1] > top2[1][1]:
    add("aggregate", "報告件数が最も多い機械はどれですか?", expected=[top2[0][0]],
        stat=f"最多機械={top2[0][0]}({top2[0][1]}件)", required_tools=[AGG_TOOLS])
# 客先で最も多い現象(一意な最大の客先を探す)
for cust in sorted({r["customer"] for r in rows}):
    sub = Counter(r["phenomenon"] for r in rows if r["customer"] == cust)
    t = sub.most_common(2)
    if sum(sub.values()) >= 8 and (len(t) == 1 or t[0][1] > t[1][1]):
        add("aggregate", f"{cust}向けで最も多い現象分類は何ですか?", expected=[t[0][0]],
            stat=f"{cust}の最多現象={t[0][0]}({t[0][1]}件)", required_tools=[AGG_TOOLS])
        break

# ---------- 3) 意味検索(説明文の一部から該当報告書を引けるか) ----------
# 説明文が長く固有性の高い行を選ぶ
uniq = sorted(rows, key=lambda r: -len(r["defect_description"]))[:40]
for r in rng.sample(uniq, 12):
    frag = unicodedata.normalize("NFKC", r["defect_description"])[:42]
    add("semantic", f"「{frag}」という内容に該当する報告書はどれですか?", gold_ids=[r["defect_id"]],
        expected=[r["defect_id"]])  # 検索は事前RAG注入で代替されるためツール必須にしない

# ---------- 4) 幻覚プローブ(存在しないものを聞く) ----------
FAB_TOOLS = DATA_TOOLS + ["list_masters", "get_statistics"]
add("fabrication", "KZ25-9999の内容を教えてください。", probe="KZ25-9999", required_tools=[DATA_TOOLS])
add("fabrication", "KZ25-0567の対策を教えてください。", probe="KZ25-0567", required_tools=[DATA_TOOLS])
add("fabrication", "TXG-9000という機械で発生した不良を教えてください。", probe="TXG-9000",
    required_tools=[DATA_TOOLS])  # 架空の存在しない機械名
add("fabrication", "客先の大和重工業向けの報告書を一覧してください。", probe="大和重工業", required_tools=[FAB_TOOLS])
add("fabrication", "作業者の卑弥呼さんが担当した不良はありますか?", probe="卑弥呼", required_tools=[FAB_TOOLS])
add("fabrication", "KZ25-8888の原因を教えてください。", probe="KZ25-8888", required_tools=[DATA_TOOLS])
add("fabrication", "KZ25-0250の報告書を要約してください。", probe="KZ25-0250", required_tools=[DATA_TOOLS])
add("fabrication", "部品「反重力スタビライザ」の不良はありますか?", probe="反重力スタビライザ", required_tools=[FAB_TOOLS])
add("fabrication", "工程「テレポート検査」で発生した不良を一覧してください。", probe="テレポート検査", required_tools=[FAB_TOOLS])
add("fabrication", "現象分類「時空歪み」の報告書は何件ありますか?", probe="時空歪み", required_tools=[FAB_TOOLS])

# ---------- 5) 画面操作(ツール呼び出しの正確性: 表示意図 → ui_* を必ず呼ぶ) ----------
r_ui = rng.sample(rows, 3)
add("ui", "サマリー画面にして", required_tools=[["ui_navigate"]])
add("ui", "週次レポートの画面を見たい", required_tools=[["ui_navigate"]])
add("ui", "是正処置の一覧を画面に出して", required_tools=[["ui_navigate"]])
add("ui", f"{r_ui[0]['machine_name']}の報告書を損失額の大きい順で一覧にして",
    required_tools=[["ui_navigate"]])
add("ui", f"{r_ui[1]['defect_id']}を画面で開いて", required_tools=[["ui_open_report", "ui_navigate"]])
add("ui", "新規報告書の作成画面を開いて", required_tools=[["ui_new_report", "ui_navigate"]])
add("ui", "ダークモードにして", required_tools=[["ui_set_theme"]])
add("ui", f"{r_ui[2]['defect_id']}の4M分析を画面で実行して",
    required_tools=[["ui_run_4m_analysis"]])
add("ui", "予測アラートの画面を見せて", required_tools=[["ui_navigate"]])
add("ui", "関連マップを画面に出して", required_tools=[["ui_navigate"]])
add("ui", "機械別の分析を損失額の大きい順で表示して", required_tools=[["ui_navigate"]])
add("ui", "時系列の分析を直近6ヶ月で見たい", required_tools=[["ui_navigate"]])
add("ui", "マスタ管理の画面を開いて", required_tools=[["ui_navigate"]])
add("ui", "2025年10月から12月のサマリーにして", required_tools=[["ui_navigate"]])
add("ui", "ライトモードにして", required_tools=[["ui_set_theme"]])

# ---------- 6) マルチターン(履歴に過去のツール結果がある状態での再取得・再操作) ----------
# 実際に観測された失敗: 会話が続いた状態で「〜を開いて」→ ツールを呼ばず内容を捏造
mt = rng.sample(rows, 18)
add("multiturn", f"{mt[1]['defect_id']}を画面で開いて",
    pre_turns=[f"{mt[0]['defect_id']}の内容を教えて"],
    required_tools=[["ui_open_report", "ui_navigate"]],
    gold_customer=mt[1]["customer"])
add("multiturn", f"{mt[3]['defect_id']}の客先はどこですか?",
    pre_turns=[f"{mt[2]['defect_id']}の内容を教えて"],
    required_tools=[DATA_TOOLS], expected=[mt[3]["customer"]], gold_ids=[mt[3]["defect_id"]])
add("multiturn", "では損失額の大きい順に並び替えて",
    pre_turns=[f"{mt[4]['machine_name']}の報告書一覧を画面に出して"],
    required_tools=[["ui_navigate"]])
add("multiturn", f"{mt[5]['defect_id']}の現象と対策を教えて",
    pre_turns=["報告件数が最も多い機械はどれですか?"],
    required_tools=[DATA_TOOLS], expected=[mt[5]["phenomenon"]], gold_ids=[mt[5]["defect_id"]])
# 3ターン目でのツール省略を検査(履歴が長いほど省略しやすい)
add("multiturn", f"{mt[8]['defect_id']}を画面で開いて",
    pre_turns=[f"{mt[6]['defect_id']}の内容を教えて", f"{mt[7]['defect_id']}の内容も教えて"],
    required_tools=[["ui_open_report", "ui_navigate"]], gold_customer=mt[8]["customer"])
add("multiturn", f"{mt[10]['defect_id']}の使用機械は?",
    pre_turns=[f"{mt[9]['defect_id']}の使用機械は?"],
    required_tools=[DATA_TOOLS], expected=[mt[10]["machine_name"]], gold_ids=[mt[10]["defect_id"]])
add("multiturn", "では未対応(open)のものだけに絞って",
    pre_turns=["報告書の一覧を画面に出して"],
    required_tools=[["ui_navigate"]])
add("multiturn", "ダークモードに切り替えて",
    pre_turns=["サマリー画面にして"],
    required_tools=[["ui_set_theme"]])
add("multiturn", f"{mt[12]['defect_id']}の対策を教えて",
    pre_turns=[f"{mt[11]['defect_id']}の対策を教えて"],
    required_tools=[DATA_TOOLS], gold_ids=[mt[12]["defect_id"]])
add("multiturn", f"{mt[14]['defect_id']}の客先と損失額を教えて",
    pre_turns=["重大度がcriticalの報告書は何件?"],
    required_tools=[DATA_TOOLS], expected=[mt[14]["customer"]], gold_ids=[mt[14]["defect_id"]])
add("multiturn", "その機械の報告書一覧を画面に出して",
    pre_turns=["報告件数が最も多い機械はどれですか?"],
    required_tools=[["ui_navigate"]])

json.dump({"seed": 0, "n_rows": len(rows), "cases": cases},
          open(HERE / "dataset.json", "w"), ensure_ascii=False, indent=1)
print(f"{len(cases)} cases -> dataset.json")
for cat in ("fact", "aggregate", "semantic", "fabrication", "ui", "multiturn"):
    print(" ", cat, sum(c["category"] == cat for c in cases))
