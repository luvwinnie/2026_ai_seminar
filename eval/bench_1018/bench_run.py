"""チャットのベンチマーク：動いている例アプリ(Docker)に全問を送り、正しさ・道具・引用・時間を記録する。

問題：eval/dataset.json(100問：fact・aggregate・semantic・fabrication・ui・multiturn)
     ＋ ontology_set.json(21問、正解は110件から計算)＋ 第4回の検索の問い16問(rag、正解の番号つき)
記録：SSE の出来事が届いた時刻(session・sources・route・tool・token・citations・done)、答え、呼んだ道具、引用、判断モデルの結果
採点(決定論。LLM を使わない)：correct・tool_ok・citation_valid(実在しない番号を作らない)・false_claim(画面操作の虚偽)・
     rag は検索の上位5件に正解が入った数(recall@5)。RAGAS は ragas_score.py で後から付ける。
作った会話は1問ごとに消す。
使い方：python bench_run.py <設定名> [--api http://localhost:8010] [--limit N]   → runs/<設定名>.jsonl
"""
import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
APP = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "decisions_1018"))
DR = re.compile(r"KZ25-\d{4}")
NEG = re.compile(r"見つかりません|存在(しません|せず|しない)|ありません|見当たりません|該当(する.*)?(報告書|データ|記録)?(は|が)?(見当たり|あり)ません|登録されていません|確認できません|該当なし|0件|０件")
CLAIM_UI = re.compile(r"(表示し|遷移し|切り替え|移動し|開き|出し)ました|切り替えました|並び替えました|一覧にしました")
norm = lambda s: unicodedata.normalize("NFKC", s or "")


def rag_cases():
    import csv
    from types import SimpleNamespace
    from eval_rerank_items import items
    rows = {r["defect_id"]: SimpleNamespace(**r) for r in csv.DictReader(open(APP / "data/defect_reports.csv", encoding="utf-8"))}
    out = []
    for qid, q, gold in items(rows):
        out.append({"id": f"rag-{qid}", "category": "rag", "question": q, "gold_ids": sorted(gold), "required_tools": None})
    return out


def load_cases():
    raw = json.loads((APP / "eval/dataset.json").read_text())
    cases = raw["cases"] if isinstance(raw, dict) else raw
    cases += json.loads((HERE / "ontology_set.json").read_text())["cases"]
    return cases + rag_cases()


def chat(api, question, session_id=None, timeout=600):
    t0 = time.monotonic()
    ev, first, answer, tools, sources = {}, {}, [], [], []
    sid = session_id
    with httpx.stream("POST", f"{api}/api/chat/stream", json={"message": question, **({"session_id": sid} if sid else {})},
                      timeout=timeout) as r:
        r.raise_for_status()
        name = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:") and name:
                d = json.loads(line[5:].strip() or "{}")
                first.setdefault(name, round(time.monotonic() - t0, 2))
                if name == "session":
                    sid = d.get("id", sid)
                elif name == "token":
                    answer.append(d.get("text", ""))
                elif name == "tool":
                    tools.append(d.get("name", ""))
                elif name == "sources":
                    sources = [s["defect_id"] for s in d.get("items", [])]
                elif name in ("route", "citations", "error"):
                    ev[name] = d
                name = None
    return {"answer": "".join(answer), "tools": tools, "sources": sources, "session_id": sid,
            "times": first, "total_s": round(time.monotonic() - t0, 2), **ev}


# 問題集(9月)の「呼ぶべき道具」は、あとから足した Ontology の道具を知らない。同じ働きの道具も正しい道具として扱う(2026-10-18)
ONT_COUNT = {"query_quality_ontology"}
ONT_FIND = {"resolve_ontology_entity", "get_ontology_object", "query_quality_ontology", "list_masters"}


def expand_tools(group):
    g = set(group)
    if g & {"get_statistics", "list_defect_reports"}:
        g |= ONT_COUNT
    if g & {"get_defect_report", "list_defect_reports", "search_defect_reports"}:
        g |= ONT_FIND
    return g


def score(case, out, valid_ids, customers):
    ans = norm(out["answer"])
    cited = list(dict.fromkeys(DR.findall(ans)))
    probe = norm(case.get("probe", ""))
    halluc = [c for c in cited if c not in valid_ids and norm(c) != probe]
    called = {t.split("_", 1)[1] if "_" in t else t for t in out["tools"]}
    req = [expand_tools(g) for g in (case.get("required_tools") or [])]
    tool_ok = all(any(t in called for t in g) for g in req)
    false_claim = bool(CLAIM_UI.search(ans)) and not any(t.startswith("ui_") for t in called)
    cat = case["category"]
    s = {"cited": cited, "hallucinated_ids": halluc, "citation_valid": not halluc, "called_tools": sorted(called),
         "tool_ok": tool_ok, "false_claim": false_claim}
    if cat == "ui":
        s["correct"] = tool_ok and not false_claim
    elif cat == "fabrication":
        s["correct"] = bool(NEG.search(ans)) and not halluc and tool_ok
    elif cat == "multiturn":
        ok = tool_ok and not false_claim and all(norm(e) in ans for e in case.get("expected", []))
        if case.get("gold_customer"):
            ok = ok and not [c for c in customers if c != case["gold_customer"] and c in ans]
        s["correct"] = ok
    elif cat == "ontology":
        hit = all(any(norm(a) in ans for a in alts) for alts in case["expected_any"])
        forbid = [f for f in case.get("forbid", []) if f in ans]
        s["correct"] = hit and tool_ok and not forbid and not halluc
        s["forbidden_hit"] = forbid
    elif cat == "rag":
        gold = set(case["gold_ids"])
        s["recall5_sources"] = (len(gold & set(out["sources"][:5])) / min(5, len(gold))) if gold else None
        s["cited_gold"] = len(gold & set(cited))
        # 正解が無い問い(報告の無い機械)は「無い」と言えたら正解。ある問いは正解の番号を1つ以上引用していれば正解
        s["correct"] = (bool(NEG.search(ans)) and not (set(cited) - {probe})) if not gold else (s["cited_gold"] > 0 and not halluc)
    else:   # fact・aggregate・semantic
        def hit(e):
            if norm(e) in ans:
                return True
            m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", e)
            return bool(m) and f"{m.group(1)}年{int(m.group(2))}月{int(m.group(3))}日" in ans
        s["correct"] = all(hit(e) for e in case.get("expected", [])) and tool_ok and not false_claim
    if out.get("citations"):
        cs = out["citations"]["checks"]
        s["cite_unsupported"] = sum(1 for c in cs if not c["supported"])
        s["cite_checked"] = len(cs)
    if out.get("route"):
        s["route_intent"] = out["route"].get("intent")
        s["route_taken"] = out["route"].get("taken")
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--api", default="http://localhost:8010")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    listing = httpx.get(f"{a.api}/api/reports", params={"limit": 500}, timeout=30).json()
    valid = {it["defect_id"] for it in listing["items"]}
    customers = sorted({it["customer"] for it in listing["items"]})
    cases = load_cases()
    if a.only:
        cases = [c for c in cases if c["category"] in a.only.split(",")]
    cases = cases[: a.limit or None]
    out_path = HERE / "runs" / f"{a.config}.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    done = {json.loads(l)["id"] for l in out_path.read_text().splitlines()} if out_path.exists() else set()
    with out_path.open("a", encoding="utf-8") as f:
        for i, c in enumerate(cases):
            if c["id"] in done:
                continue
            rec = {"id": c["id"], "category": c["category"], "question": c["question"], "config": a.config}
            sids = []
            for attempt in range(3):
                try:
                    sid = None
                    for pq in c.get("pre_turns") or []:
                        sid = chat(a.api, pq, sid)["session_id"]
                        sids.append(sid)
                    out = chat(a.api, c["question"], sid)
                    sids.append(out["session_id"])
                    if out["answer"].strip() or out.get("error"):
                        break
                except Exception as e:  # noqa: BLE001
                    out = {"answer": "", "tools": [], "sources": [], "times": {}, "total_s": None, "error": {"detail": str(e)[:200]}}
                time.sleep(3)
            rec.update({k: out.get(k) for k in ("answer", "tools", "sources", "times", "total_s", "route", "citations", "error")})
            rec["retries"] = attempt
            rec.update(score(c, out, valid, customers))
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            for sid in set(x for x in sids if x):
                try:
                    httpx.delete(f"{a.api}/api/chat/sessions/{sid}", timeout=30)
                except httpx.HTTPError:
                    pass
            print(f"[{i + 1}/{len(cases)}] {c['id']} correct={rec['correct']} tool_ok={rec['tool_ok']} "
                  f"cit={rec['citation_valid']} {rec['total_s']}s", flush=True)


if __name__ == "__main__":
    main()
