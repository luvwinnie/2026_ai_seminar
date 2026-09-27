"""分析・AI — /api/analysis(docs/04 §5)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import DefectReport
from services import llm, stats

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/alerts")
def get_alerts(db: Session = Depends(get_db)):
    """ルールベースの予兆アラート。"""
    return stats.alerts(db)


def _report_to_text(r: DefectReport) -> str:
    """4M分析用に報告書を文字列化する。"""
    return (
        f"報告書ID: {r.defect_id}\n"
        f"発生工程: {r.process} / 使用機械: {r.machine_name}\n"
        f"部品: {r.part_name}({r.part_number})\n"
        f"現象分類: {r.phenomenon}\n"
        f"不具合内容: {r.defect_description}\n"
        f"良品状態: {r.good_condition or ''}\n"
        f"原因: {r.cause or ''}\n"
        f"要因: {r.factor or ''}\n"
        f"対策: {r.countermeasure or ''}\n"
        f"再発: {'あり' if r.is_recurrence else 'なし'} / 手順書: {'あり' if r.has_procedure else 'なし'}"
    )


@router.post("/4m/{defect_id}")
def analyze_4m(defect_id: str, db: Session = Depends(get_db)):
    """Claude で 4M 分類 + 改善提案。結果を report に保存する。"""
    if not llm.is_configured():
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY が設定されていません")

    report = db.query(DefectReport).filter_by(defect_id=defect_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="報告書が見つかりません")

    result = llm.analyze_4m(_report_to_text(report))

    # 結果を報告書へ保存
    report.category_4m = result.get("category_4m")
    report.factor = result.get("factor") or report.factor
    improvements = result.get("improvements") or []
    report.ai_improvement = "\n".join(f"- {s}" for s in improvements)
    db.commit()

    return result
