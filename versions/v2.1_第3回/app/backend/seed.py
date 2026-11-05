"""起動時の取込（03_データモデル設計書.md §1.2・§6、04_API設計書.md §3.1）。"""

import csv
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import DefectReport, MasterItem

logger = logging.getLogger(__name__)

INT_COLUMNS = {"production_count", "defect_count"}
MONEY_COLUMNS = {"material_cost", "processing_cost", "outsourcing_cost", "other_cost", "total_cost"}
DATE_COLUMNS = {"occurrence_date", "report_date"}
BOOL_COLUMNS = {"is_recurrence", "has_procedure"}
TRUE_VALUES = {"true", "1", "有", "yes"}

# マスタの種類 → 報告書の列
MASTER_COLUMNS = {
    "customer": "customer",
    "process": "process",
    "machine": "machine_name",
    "operator": "operator_name",
    "phenomenon": "phenomenon",
    "factor": "factor",
}


def convert_row(row: dict[str, str]) -> dict:
    """CSV の1行（文字列）を、列ごとの型に直す。空の値は None（真偽は列の既定に任せる）。"""
    values = {}
    for column, raw in row.items():
        text = (raw or "").strip()
        if text == "":
            if column not in BOOL_COLUMNS:
                values[column] = None
            continue
        if column in INT_COLUMNS:
            values[column] = int(float(text))
        elif column in MONEY_COLUMNS:
            values[column] = float(text)
        elif column in DATE_COLUMNS:
            values[column] = date.fromisoformat(text)
        elif column in BOOL_COLUMNS:
            values[column] = text.lower() in TRUE_VALUES
        else:
            values[column] = text
    return values


def seed_reports(db: Session, csv_path: Path) -> int:
    """報告書が0件のときだけ CSV を入れる。入れた件数を返す。"""
    if db.scalar(select(func.count()).select_from(DefectReport)):
        return 0
    if not csv_path.exists():
        logger.warning("模擬データが見つかりません: %s（報告書は空のまま起動します）", csv_path)
        return 0
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reports = [DefectReport(**convert_row(row)) for row in csv.DictReader(f)]
    db.add_all(reports)
    db.commit()
    logger.info("報告書を %d 件入れました: %s", len(reports), csv_path)
    return len(reports)


def seed_masters(db: Session) -> int:
    """masters が空なら、報告書の6列の値（重複を除く）から作る。入れた件数を返す。"""
    if db.scalar(select(func.count()).select_from(MasterItem)):
        return 0
    items = []
    for category, column_name in MASTER_COLUMNS.items():
        column = getattr(DefectReport, column_name)
        seen = set()
        for name in db.scalars(select(column).distinct().where(column.is_not(None))):
            name = name.strip()
            key = name.casefold()  # 前後の空白と大文字・小文字を無視して同じ名前か比べる
            if name and key not in seen:
                seen.add(key)
                items.append(MasterItem(category=category, name=name))
    db.add_all(items)
    db.commit()
    logger.info("マスタを %d 件作りました", len(items))
    return len(items)
