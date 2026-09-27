"""報告書トリアージのグラフ(LangGraph)— 流れはコード、判断は Jev、例外だけ LLM と人。

  START → prepare → judge ─┬→ llm_review ─┐
                           └──────────────┴→ merge → plan ─┬→ draft_capa → human_review ─┬→ apply → END
                                                             └→ END                       └→ END(却下)

  prepare      コード  報告書から判断に要る項目だけを取り出す
  judge        Jev     7問を2回(不具合内容/原因)に分けて並列で聞く(約0.5秒・約0.006円)
  llm_review   LLM     閾値に届かなかった現象・要因だけを LLM に選ばせる(理由つき)。LLM が無ければ人へ
  merge        コード  登録済みの値と比べ、食い違い(分類の見直し候補)を出す
  plan         コード  客先流出、または「仕組みの原因」かつ重要度 high/critical なら CAPA へ進める
  draft_capa   LLM     処置案を下書きし、各案を Jev が3つの問いで確かめる(原因に対応・再発を防ぐ・具体的)
  human_review 人      interrupt で止まり、承認・却下と採る案を待つ(再起動しても再開できる)
  apply        コード  承認された案だけ CAPA に登録する

チェックポイントは SQLite(既定 data/triage_checkpoints.db)に毎ステップ保存する。
途中で落ちても、人の承認待ちのまま再起動しても、同じ run_id で続きから進められる。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from database import BACKEND_DIR, SessionLocal
from models import CapaAction, DefectReport, TriageRun
from services import capa_service, opencode_client, telemetry, triage
from services import decision_client as dc

logger = logging.getLogger(__name__)

CHECKPOINT_DB = Path(os.getenv("TRIAGE_CHECKPOINT_DB", str(BACKEND_DIR / "data" / "triage_checkpoints.db")))
REVIEW_KEYS = ("phenomenon", "factor")      # 閾値に届かなければ LLM に回す分類
SERIOUS = {"high", "critical"}
# 処置案の確かめ。「原因に対応しているか」を1問で聞くと遠回しで外れやすい(公式の jaggedness:間接の問い)。
# 文字どおりに答えられる3問に分け、1つでも届かなければ人が選ぶ(公式の SDE cascade:どれか1つでも引っかかれば上げる)
CAPA_CHECKS = {
    "cause": ("「処置案」は、「原因」に書かれた原因そのものを取り除く、または防ぐ内容か",
              "原因に書かれたことに直接手を打っている", "原因と関係が薄い、または一般的な注意だけ"),
    "recurrence": ("「処置案」は、手順・標準・設備・治具・教育など仕組みを変えて、同じ不適合が再び起きるのを防ぐか",
                   "仕組みを変えて再発を防ぐ", "その品物の手直し・選別・注意喚起だけ"),
    "concrete": ("「処置案」は、何を・どう変えるかが具体的に書かれていて、そのまま実行できるか",
                 "何を・どう変えるかが具体的", "「徹底する」「注意する」など抽象的"),
}
CAPA_OK = 0.7   # 3問とも、この確率以上なら「確かめ済み」として最初から選んでおく


class TriageState(TypedDict, total=False):
    run_id: str
    defect_id: str
    fields: dict            # 判断に使う報告書の項目
    registered: dict        # 登録済みの分類(比べるため)
    vocab: dict
    decisions: dict         # 項目ごとの判断(値・確率・採否・出どころ)
    jev: dict               # 呼び出しの記録(モデル・時間・費用・request id)
    llm: dict | None        # LLM に回した項目と結果
    conflicts: list[dict]   # 登録値と、確かな判断との食い違い
    escalation: dict        # CAPA へ進むか・理由
    capa_draft: dict | None # 処置案と Jev の確かめ
    review: dict | None     # 人の答え
    created_capa: list[str]
    route: list[str]        # 通ったノード


def _trail(state: TriageState, node: str) -> list[str]:
    return [*state.get("route", []), node]


# ------------------------------------------------------------------ ノード
def prepare(state: TriageState) -> dict:
    with SessionLocal() as db:
        r = db.query(DefectReport).filter_by(defect_id=state["defect_id"]).first()
        if r is None:
            raise ValueError(f"報告書 {state['defect_id']} が見つかりません")
        fields = {k: getattr(r, k) for k in ("process", "machine_name", "part_name", "defect_description",
                                            "cause", "countermeasure")}
        registered = {k: getattr(r, k) for k in ("phenomenon", "factor", "category_4m", "severity")}
        vocab = triage.vocabulary(db)
    return {"fields": fields, "registered": registered, "vocab": vocab, "route": _trail(state, "prepare")}


def judge(state: TriageState) -> dict:
    decisions, meta = triage.judge(state["fields"], state["vocab"], session_id=state["run_id"])
    telemetry.triage_step(state["run_id"], state["defect_id"], "judge", output=_brief(decisions),
                          metadata=meta, model=meta["model"])
    return {"decisions": decisions, "jev": meta, "route": _trail(state, "judge")}


def needs_review(state: TriageState) -> str:
    low = [k for k in REVIEW_KEYS if not state["decisions"].get(k, {}).get("accepted")]
    return "llm_review" if low else "merge"


def llm_review(state: TriageState) -> dict:
    """閾値に届かなかった分類だけを LLM に選ばせる(安いモデルが既定、大きいモデルは例外)。"""
    decisions = {k: dict(v) for k, v in state["decisions"].items()}
    low = [k for k in REVIEW_KEYS if not decisions.get(k, {}).get("accepted")]
    info: dict[str, Any] = {"fields": low, "backend": None}
    if opencode_client.is_configured():
        options = {k: state["vocab"][k] for k in low}
        prompt = (
            "次の不適合報告書について、指定された項目を選択肢から1つずつ選んでください。"
            "選択肢に無い値は書かないこと。判断できなければ null。\n"
            'JSON のみで返答: {"<項目>": {"value": "選択肢" | null, "reason": "1文の理由"}}\n\n'
            f"# 不具合内容\n{state['fields'].get('defect_description') or ''}\n"
            f"# 原因\n{state['fields'].get('cause') or ''}\n"
            f"# 選択肢\n{json.dumps(options, ensure_ascii=False)}\n"
            "# 参考(判断モデルの確率上位)\n"
            + json.dumps({k: decisions[k].get("top") for k in low}, ensure_ascii=False)
        )
        try:
            res = opencode_client.ask_json("あなたは製造業の品質保証エンジニアです。書かれていることだけで判断します。",
                                           prompt)
            info["backend"] = "opencode"
            for k in low:
                v = (res.get(k) or {}) if isinstance(res.get(k), dict) else {}
                if v.get("value") in state["vocab"][k]:
                    decisions[k].update({"value": v["value"], "source": "llm", "reason": v.get("reason"),
                                         "accepted": False})  # LLM の答えも、人が確かめるまでは提案のまま
            info["result"] = {k: decisions[k].get("value") for k in low}
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc)[:200]
    # 要因が変わったら、4M を対応表から引き直す
    mapped = triage.FACTOR_TO_4M.get(decisions.get("factor", {}).get("value") or "")
    if mapped and "category_4m" in decisions:
        decisions["category_4m"].update({"value": mapped, "source": "rule"})
    telemetry.triage_step(state["run_id"], state["defect_id"], "llm_review", output=info)
    return {"decisions": decisions, "llm": info, "route": _trail(state, "llm_review")}


def merge(state: TriageState) -> dict:
    conflicts = []
    for k in ("phenomenon", "factor", "category_4m"):
        d = state["decisions"].get(k) or {}
        reg = state["registered"].get(k)
        if d.get("accepted") and d.get("value") and reg and d["value"] != reg:
            conflicts.append({"field": k, "registered": reg, "suggested": d["value"],
                              "confidence": d.get("confidence")})
    return {"conflicts": conflicts, "route": _trail(state, "merge")}


def plan(state: TriageState) -> dict:
    d = state["decisions"]
    reasons = []
    outflow = d.get("outflow", {})
    systemic = d.get("systemic", {})
    severity = state["registered"].get("severity")
    if outflow.get("accepted") and outflow.get("value"):
        reasons.append("客先に届いた・客先で見つかった")
    if systemic.get("accepted") and systemic.get("value") and severity in SERIOUS:
        reasons.append(f"仕組みの原因で再発のおそれがあり、重要度が {severity}")
    with SessionLocal() as db:
        existing = db.query(CapaAction).filter_by(defect_id=state["defect_id"]).count()
    needed = bool(reasons) and existing == 0
    esc = {"needed": needed, "reasons": reasons, "existing_capa": existing}
    telemetry.triage_step(state["run_id"], state["defect_id"], "plan", output=esc)
    return {"escalation": esc, "route": _trail(state, "plan")}


def to_capa(state: TriageState) -> str:
    return "draft_capa" if state["escalation"]["needed"] else END


def draft_capa(state: TriageState) -> dict:
    with SessionLocal() as db:
        draft = capa_service.draft_actions(db, state["defect_id"])
    actions = draft.get("actions") or []
    # LLM が書いた案を Jev が確かめる(生成は LLM、判定は判断モデル)。
    # 1案ずつ別の state にして、並列に3問ずつ聞く(「処置案2は…」のような指し示しをさせない)
    if actions:
        qs = {k: dc.noul(triage.GUARD + q, true=t, false=f) for k, (q, t, f) in CAPA_CHECKS.items()}

        def check(a: dict):
            st = {"不具合内容": state["fields"].get("defect_description") or "",
                  "原因": state["fields"].get("cause") or "",
                  "処置案": f"{a.get('title') or ''}:{a.get('description') or ''}"}
            return dc.decide(st, qs, session_id=state["run_id"])

        try:
            with ThreadPoolExecutor(max_workers=min(4, len(actions))) as ex:
                results = list(ex.map(check, actions))
            for a, res in zip(actions, results):
                checks = {k: round(float(res.answers[k].value), 3) for k in CAPA_CHECKS}
                a["jev_checks"] = checks
                a["jev_fits_cause"] = checks["cause"]          # 前の画面との互換
                a["jev_ok"] = all(v >= CAPA_OK for v in checks.values())
        except dc.DecisionError as exc:
            logger.warning("処置案の確かめに失敗: %s", exc)
    out = {"actions": actions, "ai_backend": draft.get("ai_backend"),
           "similar": [s.get("defect_id") for s in draft.get("similar") or []]}
    telemetry.triage_step(state["run_id"], state["defect_id"], "draft_capa", output=out)
    return {"capa_draft": out, "route": _trail(state, "draft_capa")}


def human_review(state: TriageState) -> dict:
    """人の承認を待つ。interrupt でグラフが止まり、resume の値がここに返ってくる。"""
    answer = interrupt({"defect_id": state["defect_id"], "reasons": state["escalation"]["reasons"],
                        "actions": state["capa_draft"]["actions"]})
    review = {"approved": bool(answer.get("approved")), "selected": list(answer.get("selected") or []),
              "note": answer.get("note")}
    telemetry.triage_step(state["run_id"], state["defect_id"], "human_review", output=review)
    return {"review": review, "route": _trail(state, "human_review")}


def after_review(state: TriageState) -> str:
    return "apply" if state["review"]["approved"] and state["review"]["selected"] else END


def apply(state: TriageState) -> dict:
    actions = state["capa_draft"]["actions"]
    created = []
    with SessionLocal() as db:
        for i in state["review"]["selected"]:
            if 0 <= i < len(actions):
                a = actions[i]
                c = capa_service.create(db, {"defect_id": state["defect_id"],
                                             "action_type": a.get("action_type") or "corrective",
                                             "title": a.get("title") or "処置", "description": a.get("description")})
                created.append(c.capa_id)
    telemetry.triage_step(state["run_id"], state["defect_id"], "apply", output={"created": created})
    return {"created_capa": created, "route": _trail(state, "apply")}


def _brief(decisions: dict) -> dict:
    return {k: {kk: v.get(kk) for kk in ("value", "confidence", "probability", "accepted", "source") if kk in v}
            for k, v in decisions.items()}


# ------------------------------------------------------------------ グラフ
def build(checkpointer=None):
    g = StateGraph(TriageState)
    for name, fn in [("prepare", prepare), ("judge", judge), ("llm_review", llm_review), ("merge", merge),
                     ("plan", plan), ("draft_capa", draft_capa), ("human_review", human_review), ("apply", apply)]:
        g.add_node(name, fn)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "judge")
    g.add_conditional_edges("judge", needs_review, ["llm_review", "merge"])
    g.add_edge("llm_review", "merge")
    g.add_edge("merge", "plan")
    g.add_conditional_edges("plan", to_capa, ["draft_capa", END])
    g.add_edge("draft_capa", "human_review")
    g.add_conditional_edges("human_review", after_review, ["apply", END])
    g.add_edge("apply", END)
    return g.compile(checkpointer=checkpointer)


_graph = None
_lock = threading.Lock()


def graph():
    global _graph
    if _graph is None:
        with _lock:
            if _graph is None:
                CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
                _graph = build(SqliteSaver(conn))
    return _graph


def enabled() -> bool:
    return os.getenv("JEV_ENABLED", "").lower() in ("1", "true", "yes") and dc.is_configured()


# ------------------------------------------------------------------ 実行と保存
def _save(run_id: str, defect_id: str, status: str, result: dict) -> dict:
    with SessionLocal() as db:
        row = db.query(TriageRun).filter_by(run_id=run_id).first()
        if row is None:
            row = TriageRun(run_id=run_id, defect_id=defect_id)
            db.add(row)
        row.status = status
        row.result_json = json.dumps(result, ensure_ascii=False, default=str)
        db.commit()
    return {"run_id": run_id, "defect_id": defect_id, "status": status, **result}


def _finish(run_id: str, defect_id: str, out: dict) -> dict:
    values = graph().get_state({"configurable": {"thread_id": run_id}}).values
    keep = ("decisions", "jev", "llm", "conflicts", "escalation", "capa_draft", "review", "created_capa", "route")
    result = {k: values.get(k) for k in keep}
    if out.get("__interrupt__"):
        status = "waiting_approval"
    elif result.get("review") is not None:
        status = "approved" if result["review"]["approved"] else "rejected"
    else:
        status = "completed"
    return _save(run_id, defect_id, status, result)


def run(defect_id: str) -> dict:
    run_id = f"tr-{uuid.uuid4().hex[:12]}"
    out = graph().invoke({"run_id": run_id, "defect_id": defect_id, "route": []},
                         {"configurable": {"thread_id": run_id}})
    return _finish(run_id, defect_id, out)


def resume(run_id: str, approved: bool, selected: list[int], note: str | None = None) -> dict:
    with SessionLocal() as db:
        row = db.query(TriageRun).filter_by(run_id=run_id).first()
        if row is None:
            raise KeyError(run_id)
        if row.status != "waiting_approval":
            raise ValueError(f"この判定は承認待ちではありません(状態: {row.status})")
        defect_id = row.defect_id
    out = graph().invoke(Command(resume={"approved": approved, "selected": selected, "note": note}),
                         {"configurable": {"thread_id": run_id}})
    return _finish(run_id, defect_id, out)


def latest(defect_id: str) -> dict | None:
    with SessionLocal() as db:
        row = (db.query(TriageRun).filter_by(defect_id=defect_id).order_by(TriageRun.id.desc()).first())
        if row is None:
            return None
        return {"run_id": row.run_id, "defect_id": row.defect_id, "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                **json.loads(row.result_json or "{}")}


def preview(fields: dict) -> dict:
    """保存前の入力(新規作成のフォーム)に対する判断だけ。グラフは通さず、何も保存しない。"""
    with SessionLocal() as db:
        vocab = triage.vocabulary(db)
    decisions, meta = triage.judge(fields, vocab)
    return {"decisions": decisions, "jev": meta}


def metrics(limit: int = 10) -> dict:
    """続けて測る:報告書ごとの最新の判定と、いま登録されている値(人が確かめた値)を比べる。
    人が登録値を直すたびに数字が変わる。版や質問を変えたら、ここと eval で確かめてから閾値を動かす。"""
    keys = ("phenomenon", "factor", "category_4m")
    with SessionLocal() as db:
        latest_rows: dict[str, TriageRun] = {}
        for row in db.query(TriageRun).order_by(TriageRun.id.asc()):
            latest_rows[row.defect_id] = row
        reports = {r.defect_id: r for r in
                   db.query(DefectReport).filter(DefectReport.defect_id.in_(list(latest_rows)))}
        status_count: dict[str, int] = {}
        per = {k: {"judged": 0, "auto": 0, "auto_agree": 0} for k in keys}
        by_model: dict[str, int] = {}
        disagreements = []
        for did, row in latest_rows.items():
            status_count[row.status] = status_count.get(row.status, 0) + 1
            res = json.loads(row.result_json or "{}")
            model = (res.get("jev") or {}).get("model") or "?"
            by_model[model] = by_model.get(model, 0) + 1
            rep = reports.get(did)
            if rep is None:
                continue
            for k in keys:
                d = (res.get("decisions") or {}).get(k) or {}
                reg = getattr(rep, k)
                if not d or not reg:
                    continue
                per[k]["judged"] += 1
                if d.get("accepted"):
                    per[k]["auto"] += 1
                    if d.get("value") == reg:
                        per[k]["auto_agree"] += 1
                    elif len(disagreements) < limit:
                        disagreements.append({"defect_id": did, "field": k, "registered": reg,
                                              "suggested": d.get("value"), "p_top": d.get("p_top"),
                                              "margin": d.get("margin"), "run_id": row.run_id})
    fields = {k: {**v, "auto_rate": round(v["auto"] / v["judged"], 3) if v["judged"] else None,
                  "agreement": round(v["auto_agree"] / v["auto"], 3) if v["auto"] else None}
              for k, v in per.items()}
    return {"reports": len(latest_rows), "status": status_count, "models": by_model,
            "measured_model": triage.measured_model(), "fields": fields, "disagreements": disagreements}
