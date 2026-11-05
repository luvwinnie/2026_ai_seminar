"""Ontology の問いのセットを作る(正解は data/defect_reports.csv の110件と、動いているアプリの是正処置から計算)。
あわせて、LLM を通さずに Ontology の道具(MCP)を直接呼び、正解と合うかを確かめる(道具だけの試験)。

使い方：python make_ontology_set.py [http://localhost:8010]   → ontology_set.json・tool_eval.json
"""
import asyncio
import csv
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent.parent
API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8010"
rows = list(csv.DictReader(open(APP / "data" / "defect_reports.csv", encoding="utf-8")))
I = lambda v: int(float(v or 0))


def sub(f):
    return [r for r in rows if f(r)]


def rate(rs):
    p, d = sum(I(r["production_count"]) for r in rs), sum(I(r["defect_count"]) for r in rs)
    return d, p, (d / p if p else None)


def pct(x):
    return [f"{x * 100:.1f}%", f"{x * 100:.2f}%", f"{round(x * 100)}%"] if x is not None else []


def yen(v):
    return [f"{v:,}円", f"{v:,}", f"{v}円"]


def n(v, unit="件"):
    return [f"{v}{unit}", f"{v} {unit}"]


C = lambda key: Counter(r[key] for r in rows)
Q = []


def add(qid, q, expect, tools, kind, tool_check=None, forbid=None):
    Q.append({"id": qid, "category": "ontology", "kind": kind, "question": q, "expected_any": expect,
              "required_tools": [tools], "tool_check": tool_check, "forbid": forbid or []})


ONT_COUNT = ["query_quality_ontology", "get_statistics", "list_defect_reports"]
for m in ("a61nx", "GENOS M660-V", "QUICK TURN 250MSY", "TSL-550"):
    k = len(sub(lambda r: r["machine_name"] == m))
    add(f"ont-count-{m}", f"{m} の不適合報告書は何件ありますか？", [n(k)], ONT_COUNT, "count",
        {"tool": "query", "machine": m, "metric": "report_count", "value": k})
for m in ("GENOS M560-V", "TXG-9000"):
    add(f"ont-none-{m}", f"{m} の不適合報告書は何件ありますか？", [["0件", "0 件", "ありません", "存在しません", "見つかりません", "登録されていません"]],
        ["resolve_ontology_entity", "list_defect_reports", "query_quality_ontology", "get_statistics", "list_masters"], "no_substitution",
        {"tool": "resolve", "machine": m, "expect_none": True}, forbid=["GENOS M660-V"] if "GENOS" in m else ["MEGATURN NEXUS 900"])
for m in ("a61nx", "汎用フライス"):
    d, p, x = rate(sub(lambda r: r["machine_name"] == m))
    add(f"ont-rate-{m}", f"{m} の不良率(不適合数の合計÷加工数の合計)は？", [pct(x)], ONT_COUNT, "rate",
        {"tool": "query", "machine": m, "metric": "recorded_defect_rate", "value": round(x, 4)})
d, p, x = rate(rows)
add("ont-rate-all", "全体の不良率(不適合数の合計÷加工数の合計)は？", [pct(x)], ONT_COUNT, "rate")
loss = sum(I(r["total_cost"]) for r in sub(lambda r: r["machine_name"] == "YZ-8WR"))
add("ont-loss-YZ-8WR", "YZ-8WR の報告書の損失合計は何円？", [yen(loss)], ONT_COUNT, "sum",
    {"tool": "query", "machine": "YZ-8WR", "metric": "known_loss_jpy", "value": loss})
proc = C("process").most_common(1)[0]
add("ont-top-process", "工程別で不適合報告書が一番多い工程と件数は？", [[proc[0]], n(proc[1])], ONT_COUNT, "group")
cust = C("customer").most_common(1)[0]
add("ont-top-customer", "客先別で不適合報告書が一番多い客先と件数は？", [[cust[0]], n(cust[1])], ONT_COUNT, "group")
m4 = C("category_4m")
add("ont-4m-man", "4M分類が Man(人)の報告書は何件？", [n(m4["Man"])], ONT_COUNT, "count")
add("ont-crit", "重大度が critical(重大)の報告書は何件？", [n(C("severity")["critical"])], ONT_COUNT, "count")
add("ont-open", "状態が未対応(open)の報告書は何件？", [n(C("status")["open"])], ONT_COUNT, "count")
rec = sum(1 for r in rows if r["is_recurrence"].lower() in ("true", "1"))
add("ont-recur", "再発ありの報告書は何件？", [n(rec)], ONT_COUNT, "count")
sep = sub(lambda r: r["occurrence_date"].startswith("2025-09"))
add("ont-2025-09", "2025年9月に発生した報告書は何件？", [n(len(sep))], ONT_COUNT, "count")
a9 = [r["defect_id"] for r in sep if r["machine_name"] == "a61nx"]
add("ont-a61nx-2025-09", "a61nx で2025年9月に発生した報告書はどれ？", [a9], ONT_COUNT, "filter")
add("ont-surface", "現象が表面キズの報告書は何件？", [n(C("phenomenon")["表面キズ"])], ONT_COUNT, "count")
sui = sub(lambda r: r["customer"] == "翠峰重工業")
add("ont-cust-count", "翠峰重工業向けの不適合報告書は何件？", [n(len(sui))], ONT_COUNT, "count",
    {"tool": "query", "customer": "翠峰重工業", "metric": "report_count", "value": len(sui)})
sp = Counter(r["process"] for r in sui).most_common(1)[0]
add("ont-cust-process", "翠峰重工業向けの不適合は、どの工程で一番多い？", [[sp[0]]], ONT_COUNT, "group")


async def capa_and_tools():
    from fastmcp import Client
    out = []
    async with Client(f"{API}/mcp/") as c:
        # 是正処置(CAPA)の問いは入れない:動いているアプリの7件はすべて 2026-09-09 の動作確認の試しのデータで、
        # 今の110件に無い報告書(KZ25-0118)に付いている(残っている記録。消すかどうかはユーザーが決める)
        caps = (await c.call_tool("list_capa_actions", {})).structured_content
        out.append({"id": "capa-data", "ok": None, "note": f"CAPA {caps.get('total')} 件(すべて試しのデータ。問いから外した)"})
        # 道具だけの試験
        ids = {}
        for q in Q:
            tc = q.get("tool_check")
            if not tc:
                continue
            try:
                if tc["tool"] == "resolve":
                    r = (await c.call_tool("resolve_ontology_entity", {"object_type": "MachineLabel", "query": tc["machine"]})).structured_content
                    ok = (r["total"] == 0 and not r["can_auto_select"]) if tc.get("expect_none") else bool(r["candidates"])
                    out.append({"id": q["id"], "ok": ok, "got": {"total": r["total"], "can_auto_select": r["can_auto_select"]}})
                    continue
                kind, name = ("MachineLabel", tc["machine"]) if "machine" in tc else ("Customer", tc["customer"])
                r = (await c.call_tool("resolve_ontology_entity", {"object_type": kind, "query": name})).structured_content
                oid = r["candidates"][0]["object_id"]
                scope = {"machine_id": oid} if kind == "MachineLabel" else {"customer_id": oid}
                res = (await c.call_tool("query_quality_ontology", {"scope": scope})).structured_content
                got = res["metrics"].get(tc["metric"])
                got_v = float(got) if got is not None else None
                ok = got_v is not None and abs(got_v - float(tc["value"])) < 1e-3 * max(1, abs(float(tc["value"])))
                out.append({"id": q["id"], "ok": ok, "metric": tc["metric"], "got": got, "want": tc["value"]})
            except Exception as e:  # noqa: BLE001
                out.append({"id": q["id"], "ok": False, "error": str(e)[:200]})
    return out


tool = asyncio.run(capa_and_tools())
(HERE / "ontology_set.json").write_text(json.dumps({"cases": Q}, ensure_ascii=False, indent=1), encoding="utf-8")
(HERE / "tool_eval.json").write_text(json.dumps(tool, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(Q), "questions")
for t in tool:
    print(("OK " if t["ok"] else "NG "), json.dumps(t, ensure_ascii=False))
