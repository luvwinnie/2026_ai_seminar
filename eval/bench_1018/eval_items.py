"""RAGAS 用の環境から、検索の問い(rag-…)の正解の番号を読む(backend を import しない)。"""
import csv
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "decisions_1018"))
from eval_rerank_items import items  # noqa: E402

_rows = {r["defect_id"]: SimpleNamespace(**r) for r in csv.DictReader(open(HERE.parent.parent / "data/defect_reports.csv", encoding="utf-8"))}
GOLD = {f"rag-{qid}": sorted(g) for qid, q, g in items(_rows)}


def rag_gold(rid):
    return GOLD.get(rid, [])
