# -*- coding: utf-8 -*-
"""RAG回答品質評価 — 実チャットパイプライン(OpenCode+OpenRouter+MCP)を通し、
架空データのGround Truthで決定論的スコア + RAGAS準拠のLLM判定を行う。

決定論的指標(設定判断用・LLM を使わず機械的に判定):
  - correct        : 期待値(機械名/件数/ID等)が回答に含まれるか
  - citation_valid : 回答中の KZ25-XXXX が全て実在するか(幻覚ID検出)
  - fabrication_ok : 存在しない対象に「見つからない」と答えられたか
LLM判定(RAGAS準拠, OpenRouter judge):
  - faithfulness   : 回答の主張がGround Truthデータで裏付けられるか(幻覚検出) 0-1
  - relevancy      : 回答が質問に答えているか 0-1

実行: ../.venv/bin/python run_eval.py [--limit N] [--no-judge]
出力: results.json / report.md
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import httpx

HERE = Path(__file__).parent
BASE = os.environ.get("APP_URL", "http://localhost:5373")
DATASET = json.load(open(HERE / "dataset.json", encoding="utf-8"))
VALID_IDS = None  # 起動時にAPIから取得
KNOWN_CUSTOMERS: list = []

# OpenRouter judge
ENV = {}
for line in open(HERE.parent / ".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        ENV[k] = v.strip()
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "openai/gpt-4o-mini")
DR_RE = re.compile(r"KZ25-\d{4}")
NEG_RE = re.compile(r"見つかりません|存在(しません|せず|しない)|ありません|見当たりません|該当(する.*)?(報告書|データ|記録)?(は|が)?(見当たり|あり)ません|登録されていません|確認できません|該当なし")


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def chat(question: str, timeout=240, session_id=None) -> dict:
    """チャットSSEを叩き、answer / sources / tools / session_id を返す。"""
    answer, sources, tools = [], [], []
    payload = {"message": question}
    if session_id is not None:
        payload["session_id"] = session_id
    with httpx.stream("POST", f"{BASE}/api/chat/stream",
                      json=payload, timeout=timeout) as r:
        r.raise_for_status()
        event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: ") and event:
                data = json.loads(line[6:])
                if event == "token":
                    answer.append(data.get("text") or data.get("delta") or "")
                elif event == "sources":
                    sources = data.get("items", [])
                elif event == "tool":
                    tools.append(data.get("name", ""))
                elif event == "error":
                    raise RuntimeError(data.get("detail"))
                elif event == "session":
                    session_id = data.get("id", session_id)
                elif event == "done":
                    break
    return {"answer": "".join(answer), "sources": sources, "tools": tools,
            "session_id": session_id}


def judge(question: str, answer: str, context: str) -> dict:
    """RAGAS準拠のLLM判定(faithfulness / relevancy)。"""
    prompt = f"""あなたはRAG回答の採点者です。以下を0.0〜1.0で採点し、JSONだけを返してください。
- faithfulness: 回答の事実主張がコンテキスト(正解データ)で裏付けられる割合。裏付けの無い主張(幻覚)があれば下げる
- relevancy: 回答が質問に直接答えているか

# 質問
{question}

# コンテキスト(正解データ)
{context[:4000]}

# 回答
{answer[:3000]}

JSON形式: {{"faithfulness": 0.0, "relevancy": 0.0, "reason": "短い理由"}}"""
    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {ENV['OPENROUTER_API_KEY']}"},
        json={"model": JUDGE_MODEL, "temperature": 0,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {"faithfulness": None, "relevancy": None, "reason": "parse error"}


def build_context(case: dict, cited: list[str]) -> str:
    """判定用コンテキスト = gold行 + 引用行の実データ + 集計の正解。"""
    parts = []
    if case.get("stat"):
        parts.append(f"[正解の集計] {case['stat']}")
    for did in dict.fromkeys((case.get("gold_ids") or []) + cited[:5]):
        if did not in VALID_IDS:
            parts.append(f"[{did}] このIDの報告書は存在しない")
            continue
        r = httpx.get(f"{BASE}/api/reports/{did}", timeout=30).json()
        parts.append(f"[{did}] 機械={r.get('machine_name')} 客先={r.get('customer')} "
                     f"工程={r.get('process')} 現象={r.get('phenomenon')} 部品={r.get('part_name')} "
                     f"内容={norm(r.get('defect_description') or '')[:200]}")
    return "\n".join(parts) or "(コンテキストなし)"


def main():
    global VALID_IDS
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--only", type=str, default="", help="カテゴリ名のカンマ区切りで絞り込み")
    args = ap.parse_args()

    listing = httpx.get(f"{BASE}/api/reports", params={"limit": 500}, timeout=30).json()
    VALID_IDS = {it["defect_id"] for it in listing["items"]}
    global KNOWN_CUSTOMERS
    KNOWN_CUSTOMERS = sorted({it["customer"] for it in listing["items"]})
    print(f"valid ids: {len(VALID_IDS)}")

    cases = DATASET["cases"]
    if args.only:
        want = set(args.only.split(","))
        cases = [c for c in cases if c["category"] in want]
    cases = cases[: args.limit or None]
    results = []
    for i, case in enumerate(cases):
        t0 = time.time()
        def _ask_with_retry():
            """空応答・一過性エラーは3回までリトライ(インフラ揺らぎとモデル性能を分離する)。"""
            last = None
            for attempt in range(3):
                try:
                    if case.get("pre_turns"):
                        sid = None
                        for pq in case["pre_turns"]:
                            sid = chat(pq, session_id=sid)["session_id"]
                        o = chat(case["question"], session_id=sid)
                    else:
                        o = chat(case["question"])
                    if o["answer"].strip():
                        if attempt:
                            o["retries"] = attempt
                        return o
                    last = RuntimeError("empty answer")
                except Exception as e:  # noqa: BLE001
                    last = e
                time.sleep(4 * (attempt + 1))
            raise last

        try:
            out = _ask_with_retry()
        except Exception as e:
            results.append({**case, "error": str(e)})
            print(f"[{i+1}/{len(cases)}] {case['id']} ERROR {e}", flush=True)
            continue
        ans = norm(out["answer"])
        cited = list(dict.fromkeys(DR_RE.findall(ans)))
        # 幻覚ID = 実在しない引用。ただし fabrication では「質問されたID自体への言及」
        # (例:「KZ25-9999は存在しません」)は否定のための言及であり幻覚ではない
        probe = norm(case.get("probe", ""))

        def _is_hypothetical(cid: str) -> bool:
            """「例: KZ25-0999 など」のような仮定・例示中の言及は、実在主張ではないので幻覚に数えない。"""
            for m in re.finditer(re.escape(cid), ans):
                ctx = ans[max(0, m.start() - 20): m.end() + 20]
                if not re.search(r"例[::]|たとえば|例えば|など|誤り|間違|タイプミス|でしょうか[??]", ctx):
                    return False  # 例示でない言及が1つでもあれば幻覚扱い
            return True

        hallucinated = [
            c for c in cited
            if c not in VALID_IDS and norm(c) != probe and not _is_hypothetical(c)
        ]
        # --- ツール呼び出しの採点 ---
        # SSEのツール名は "defect-reports_get_defect_report" 形式なので接頭辞を除去
        called = {t.split("_", 1)[1] if "_" in t else t for t in out["tools"]}
        required = case.get("required_tools") or []
        tool_ok = all(any(t in called for t in group) for group in required)
        # 虚偽主張検出: 画面操作を主張したのに ui_* を一度も呼んでいない
        claimed_ui = bool(re.search(r"(表示し|遷移し|切り替え|移動し|開き|出し)ました|切り替えました|並び替えました|一覧にしました", ans))
        ui_called = any(t.startswith("ui_") for t in called)
        false_claim = claimed_ui and not ui_called
        rec = {**case, "answer": out["answer"], "tools": out["tools"],
               "called_tools": sorted(called), "tool_ok": tool_ok, "false_claim": false_claim,
               "cited": cited, "hallucinated_ids": hallucinated,
               "citation_valid": not hallucinated, "sec": round(time.time() - t0, 1)}

        if case["category"] == "multiturn":
            ok = tool_ok and not false_claim
            if case.get("expected"):
                ok = ok and all(norm(e) in ans for e in case["expected"])
            # 履歴からの捏造検出: 実在客先名を挙げるなら正解行の客先のみ許す
            if case.get("gold_customer"):
                others = [c for c in KNOWN_CUSTOMERS if c != case["gold_customer"] and c in ans]
                ok = ok and not others
            rec["correct"] = ok
        elif case["category"] == "ui":
            # 画面操作: 必須ツールを実際に呼び、虚偽主張がないこと
            rec["correct"] = tool_ok and not false_claim
        elif case["category"] == "fabrication":
            # 「見つからない」と明言し、かつ(プローブ以外の)幻覚IDを主張していないこと。
            # かつ実際にDBを確認していること(ツール0回で否定はNG)
            rec["fabrication_ok"] = bool(NEG_RE.search(ans)) and not hallucinated and tool_ok
            rec["correct"] = rec["fabrication_ok"]
        else:
            def _hit(e: str) -> bool:
                if norm(e) in ans:
                    return True
                m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", e)
                if m:  # 日付は「2025年11月26日」表記も正答扱い
                    y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
                    return f"{y}年{mo}月{d}日" in ans
                return False
            rec["correct"] = (all(_hit(e) for e in case.get("expected", []))
                              and tool_ok and not false_claim)

        if not args.no_judge and case["category"] not in ("fabrication", "ui", "multiturn"):
            try:
                ctx = build_context(case, cited)
                rec["judge"] = judge(case["question"], out["answer"], ctx)
            except Exception as e:
                rec["judge"] = {"error": str(e)}

        results.append(rec)
        j = rec.get("judge") or {}
        print(f"[{i+1}/{len(cases)}] {case['id']} correct={rec['correct']} "
              f"tool_ok={rec['tool_ok']} cit_ok={rec['citation_valid']} "
              f"faith={j.get('faithfulness')} ({rec['sec']}s)"
              + (" ⚠虚偽主張" if rec["false_claim"] else ""), flush=True)

    json.dump(results, open(HERE / "results.json", "w"), ensure_ascii=False, indent=1)

    # ---- レポート ----
    def rate(xs):
        xs = [x for x in xs if x is not None]
        return f"{sum(xs)/len(xs)*100:.0f}% ({sum(xs)}/{len(xs)})" if xs else "-"

    lines = ["# RAG回答品質 評価レポート", "",
             f"- 実行: {time.strftime('%Y-%m-%d %H:%M')} / モデル: OpenCode+OpenRouter(本番同等) / judge: {JUDGE_MODEL}",
             f"- データ: 架空117件(霧沢精機) を Ground Truth に {len(results)} ケース", ""]
    lines.append("| カテゴリ | 正答率 | ツール正答率 | 引用の妥当性 | faithfulness平均 | relevancy平均 |")
    lines.append("|---|---|---|---|---|---|")
    for cat in ("fact", "aggregate", "semantic", "fabrication", "ui", "multiturn"):
        sub = [r for r in results if r["category"] == cat and "error" not in r]
        if not sub:
            continue
        f_ = [r.get("judge", {}).get("faithfulness") for r in sub if isinstance(r.get("judge", {}).get("faithfulness"), (int, float))]
        rel = [r.get("judge", {}).get("relevancy") for r in sub if isinstance(r.get("judge", {}).get("relevancy"), (int, float))]
        fa = f"{sum(f_)/len(f_):.2f}" if f_ else "-"
        ra = f"{sum(rel)/len(rel):.2f}" if rel else "-"
        lines.append(f"| {cat} | {rate([r['correct'] for r in sub])} | {rate([r['tool_ok'] for r in sub])} | "
                     f"{rate([r['citation_valid'] for r in sub])} | {fa} | {ra} |")
    bad = [r for r in results if not r.get("correct")]
    if bad:
        lines += ["", "## 不正解ケース"]
        for r in bad:
            lines.append(f"- **{r['id']}** {r['question']} → 期待:{r.get('expected') or r.get('probe')} / "
                         f"回答冒頭: {norm(r.get('answer',''))[:120]}…")
    fc = [r for r in results if r.get("false_claim")]
    lines += ["", f"## 虚偽主張(画面操作を主張したのにui_*未呼び出し): {len(fc)}件"]
    for r in fc:
        lines.append(f"- {r['id']}: {r['question']}")
    ntool = [r for r in results if not r.get("tool_ok", True)]
    lines += ["", f"## ツール未呼び出し(必須ツール不使用): {len(ntool)}件"]
    for r in ntool:
        lines.append(f"- {r['id']}: 必須{r.get('required_tools')} / 実際{r.get('called_tools')}")
    halluc = [r for r in results if r.get("hallucinated_ids")]
    lines += ["", f"## 幻覚ID(存在しないKZ25-XXXXの引用): {len(halluc)}件"]
    for r in halluc:
        lines.append(f"- {r['id']}: {r['hallucinated_ids']}")
    open(HERE / "report.md", "w").write("\n".join(lines))
    print("saved: results.json / report.md")


if __name__ == "__main__":
    main()
