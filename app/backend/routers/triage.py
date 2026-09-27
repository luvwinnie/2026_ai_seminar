"""報告書トリアージ REST — /api/triage(判断モデル Jev + LangGraph)。

  GET  /api/triage/status                 使えるか・モデル・閾値・呼び出しの記録
  POST /api/triage/preview                保存前の入力(新規作成のフォーム)への判断だけ。何も保存しない
  POST /api/triage/reports/{defect_id}    1件をグラフに通す(承認が要れば waiting_approval で止まる)
  GET  /api/triage/reports/{defect_id}    その報告書の最新の結果
  POST /api/triage/runs/{run_id}/resume   人の承認・却下で、止まっていたグラフを続きから進める
  GET  /api/triage/metrics                最新の判定と、いまの登録値(人が確かめた値)の一致率(続けて測る)

JEV_ENABLED=1 と、TYPESAFE_API_KEY か OPENROUTER_API_KEY があるときだけ動く(無ければ 503)。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import decision_client as dc
from services import triage, triage_graph

router = APIRouter(prefix="/api/triage", tags=["triage"])


class PreviewIn(BaseModel):
    defect_description: str = Field(..., min_length=1)
    cause: str | None = None
    countermeasure: str | None = None
    process: str | None = None
    machine_name: str | None = None
    part_name: str | None = None


class ResumeIn(BaseModel):
    approved: bool
    selected: list[int] = []
    note: str | None = None


def _require():
    if not triage_graph.enabled():
        raise HTTPException(status_code=503, detail="トリアージは無効です(JEV_ENABLED=1 と判断モデルのキーが必要)")


@router.get("/status")
def status():
    return {"enabled": triage_graph.enabled(), "backend": dc.backend_name(), "model": dc.model_name(),
            "measured_model": triage.measured_model(), "zdr": dc.zdr_enabled(),
            "thresholds": triage.thresholds(), "margins": triage.margins(), "ledger": dc.ledger()}


@router.get("/metrics")
def metrics():
    return triage_graph.metrics()


@router.post("/preview")
def preview(payload: PreviewIn):
    _require()
    try:
        return triage_graph.preview(payload.model_dump())
    except dc.DecisionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/reports/{defect_id}")
def run(defect_id: str):
    _require()
    try:
        return triage_graph.run(defect_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except dc.DecisionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/reports/{defect_id}")
def latest(defect_id: str):
    r = triage_graph.latest(defect_id)
    if r is None:
        raise HTTPException(status_code=404, detail="まだ判定していません")
    return r


@router.post("/runs/{run_id}/resume")
def resume(run_id: str, payload: ResumeIn):
    _require()
    try:
        return triage_graph.resume(run_id, payload.approved, payload.selected, payload.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="判定が見つかりません") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
