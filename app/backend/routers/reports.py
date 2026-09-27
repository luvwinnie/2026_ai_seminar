"""報告書 CRUD — /api/reports(docs/04 §2)。

作成・更新・絞り込みの実体は services/report_service.py(MCPツールと共用)。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import DefectReport
from schemas import (
    ReportCreate,
    ReportList,
    ReportOut,
    ReportUpdate,
    SmartSearchResponse,
)
from services import rag
from services.report_service import (
    ReportServiceError,
    build_report_query,
    create_report_core,
    update_report_core,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("", response_model=ReportList)
def list_reports(
    db: Session = Depends(get_db),
    q: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    machine: str | None = None,
    process: str | None = None,
    customer: str | None = None,
    operator: str | None = None,
    phenomenon: str | None = None,
    category_4m: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = "-occurrence_date",
):
    """一覧(フィルタ・ソート・ページング)。"""
    query = build_report_query(
        db,
        q=q,
        status=status,
        severity=severity,
        machine=machine,
        process=process,
        customer=customer,
        operator=operator,
        phenomenon=phenomenon,
        category_4m=category_4m,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
    )
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return {"total": total, "items": items}


@router.post("", response_model=ReportOut, status_code=201)
def create_report(payload: ReportCreate, db: Session = Depends(get_db)):
    """新規作成。defect_id 未指定なら採番し、Chroma へ upsert。"""
    try:
        return create_report_core(db, payload.model_dump(exclude_unset=False))
    except ReportServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/search", response_model=SmartSearchResponse)
def smart_search(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1),
    top_k: int = Query(10, ge=1, le=40),
    machine: str | None = None,
    process: str | None = None,
):
    """スマート検索(意味検索)。ハイブリッド検索(rag.search)で自然文から類似報告書を返す。

    machine / process 指定時は検索結果を後段で絞り込む(MCP search_defect_reports と同方式)。
    ※ /{defect_id} より前に定義すること(ルーティング順)。
    """
    fetch = top_k * 4 if (machine or process) else top_k
    results = rag.search(db, q, top_k=min(fetch, 40))
    items = []
    for r in results:
        if machine and r.get("machine_name") != machine:
            continue
        if process and r.get("process") != process:
            continue
        items.append(r)
        if len(items) >= top_k:
            break
    mode = items[0]["search_mode"] if items else (results[0]["search_mode"] if results else "keyword")
    return {"items": items, "search_mode": mode}


@router.get("/{defect_id}/similar")
def similar_reports(defect_id: str, top_k: int = Query(3, ge=1, le=10), db: Session = Depends(get_db)):
    """類似事例サジェスト(docs/10 A-1) — この報告書に似た過去事例と「当時の対策」を返す。

    ハイブリッド検索(rag.search)に本文+現象を投げ、自分自身を除いた上位を、
    対策(countermeasure)全文付きで返す。起票・調査の出発点を豊かにする用途。
    """
    base = db.query(DefectReport).filter_by(defect_id=defect_id).first()
    if base is None:
        raise HTTPException(status_code=404, detail=f"{defect_id} は見つかりません")
    query_text = " ".join(filter(None, [base.phenomenon, base.defect_description, base.cause]))
    hits = rag.search(db, query_text, top_k=top_k + 3)
    ids = [h["defect_id"] for h in hits if h["defect_id"] != defect_id][:top_k]
    rows = {r.defect_id: r for r in db.query(DefectReport).filter(DefectReport.defect_id.in_(ids)).all()}
    items = []
    for h in hits:
        r = rows.get(h["defect_id"])
        if r is None:
            continue
        items.append(
            {
                "defect_id": r.defect_id,
                "occurrence_date": r.occurrence_date.isoformat() if r.occurrence_date else None,
                "part_name": r.part_name,
                "machine_name": r.machine_name,
                "process": r.process,
                "phenomenon": r.phenomenon,
                "cause": (r.cause or "")[:160],
                "countermeasure": (r.countermeasure or "")[:240],
                "score": h["score"],
            }
        )
    return {"defect_id": defect_id, "items": items}


@router.get("/{defect_id}", response_model=ReportOut)
def get_report(defect_id: str, db: Session = Depends(get_db)):
    """詳細(defect_rate 含む)。"""
    report = db.query(DefectReport).filter_by(defect_id=defect_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")
    return report


@router.put("/{defect_id}", response_model=ReportOut)
def update_report(defect_id: str, payload: ReportUpdate, db: Session = Depends(get_db)):
    """部分更新(渡されたフィールドのみ)。Chroma 再 upsert。"""
    report = db.query(DefectReport).filter_by(defect_id=defect_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")
    return update_report_core(db, report, payload.model_dump(exclude_unset=True))


@router.delete("/{defect_id}", status_code=204)
def delete_report(defect_id: str, db: Session = Depends(get_db)):
    """削除(Chroma からも削除)。"""
    report = db.query(DefectReport).filter_by(defect_id=defect_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")
    db.delete(report)
    db.commit()
    rag.delete(defect_id)
    return None
