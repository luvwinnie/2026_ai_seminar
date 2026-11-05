"""③ 引用の確かめの問題(eval_cite.py と同じ54組。乱数は固定)。"""
import csv
import random
from types import SimpleNamespace

from common import APP


def items():
    rows = list(csv.DictReader(open(APP / "data" / "defect_reports.csv", encoding="utf-8")))
    R = {r["defect_id"]: SimpleNamespace(**r) for r in rows}
    rnd = random.Random(20261018)
    pick = rnd.sample(rows, 24)
    P = []
    for k, r in enumerate(pick):
        other = lambda key: rnd.choice([x for x in rows if x[key] != r[key]])[key]
        i = r["defect_id"]
        t = k % 4
        if t == 0:
            P.append(("machine_phen", True, f"[{i}] では、{r['machine_name']} で{r['phenomenon']}が起きた。", i))
            P.append(("machine_swap", False, f"[{i}] では、{other('machine_name')} で{r['phenomenon']}が起きた。", i))
        elif t == 1:
            P.append(("cause", True, f"[{i}] の原因は「{r['cause']}」とされている。", i))
            P.append(("cause_swap", False, f"[{i}] の原因は「{other('cause')}」とされている。", i))
        elif t == 2:
            P.append(("count", True, f"[{i}] では、加工数{r['production_count']}個のうち{r['defect_count']}個が不適合だった。", i))
            P.append(("count_swap", False, f"[{i}] では、加工数{r['production_count']}個のうち{int(r['defect_count']) + 3}個が不適合だった。", i))
        else:
            P.append(("phen", True, f"[{i}] の現象は{r['phenomenon']}で、対策は「{r['countermeasure'][:40]}」などである。", i))
            P.append(("phen_swap", False, f"[{i}] の現象は{other('phenomenon')}で、対策は「{r['countermeasure'][:40]}」などである。", i))
    for r in [x for x in rows if "欠けを後で確認した" in x["defect_description"]][:8]:
        P.append(("shift", False, f"[{r['defect_id']}] では、工具チップの欠けが原因で{r['phenomenon']}が起きた。", r["defect_id"]))
        P.append(("shift_ok", True, f"[{r['defect_id']}] では、{r['phenomenon']}のあとで工具チップの欠けも確認された。", r["defect_id"]))
    return P, R
