"""帳票取り込み — /api/ingest(docs/04 §3)。

- xlsx: openpyxl でラベルセルを走査して抽出(API キーがあれば Claude で補正)。
- pdf / 画像: Claude vision + structured outputs(API キー未設定時は 503)。
保存はせず、確認画面用に extracted を返す。
"""
from __future__ import annotations

import io
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from schemas import IngestResult, ReportCreate, ReportOut
from services import llm

from . import reports as reports_router

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# 帳票ラベル → API フィールド名(値はラベルセルの右隣)
_LABEL_MAP = {
    "発生日": "occurrence_date",
    "報告日": "report_date",
    "客先": "customer",
    "発見者名": "discoverer",
    "発生工程": "process",
    "使用機械": "machine_name",
    "作業者名": "operator_name",
    "重要度": "severity",
    "部品番号": "part_number",
    "部品名称": "part_name",
    "加工数": "production_count",
    "不適合数": "defect_count",
    "現象": "phenomenon",
    "要因": "factor",
    "4M分類": "category_4m",
    "状態": "status",
    "不具合内容": "defect_description",
    "良品状態": "good_condition",
    "原因": "cause",
    "対策": "countermeasure",
    "手順書有無": "has_procedure",
    "再発": "is_recurrence",
    "備考": "notes",
    # 様式 QF-07-03(2026年版帳票)のラベル表記
    "発行日": "report_date",
    "発見者": "discoverer",
    "作業者": "operator_name",
    "重大度": "severity",
    "品名": "part_name",
    "材料費": "material_cost",
    "加工費": "processing_cost",
    "外注費": "outsourcing_cost",
    "損失合計": "total_cost",
}

# QF-07-03: セクション見出しに埋め込まれた属性と、見出し直下の本文ブロック
_SECTION_TEXT = {
    "不適合内容": "defect_description",
    "良品状態": "good_condition",
    "原因": "cause",
    "対策": "countermeasure",
}
_RE_PHENOM = re.compile(r"現象[::]\s*([^))/]+)")
_RE_FACTOR = re.compile(r"要因[::]\s*([^))/]+)")
_RE_4M = re.compile(r"4M[::]\s*(Man|Machine|Material|Method)")
_RE_QTY = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")

# 費用ブロック: ラベルは上、値は真下のセル
_COST_MAP = {
    "材料費": "material_cost",
    "社内加工費": "processing_cost",
    "外注加工費": "outsourcing_cost",
    "その他": "other_cost",
    "合計": "total_cost",
}

_INT_FIELDS = {"production_count", "defect_count"}
_FLOAT_FIELDS = {"material_cost", "processing_cost", "outsourcing_cost", "other_cost", "total_cost"}
_BOOL_FIELDS = {"has_procedure", "is_recurrence"}


def _to_number(value):
    if value is None:
        return None
    return str(value).replace(",", "").replace("円", "").strip()


_4M_VALUES = {"Man", "Machine", "Material", "Method"}


def _coerce(field: str, value):
    """フィールド型に合わせて値を変換する。"""
    if value is None or value == "":
        return None
    # 4M分類は正規の4値のみ許可。帳票の「(未分類)」等は None にする
    if field == "category_4m" and str(value).strip() not in _4M_VALUES:
        return None
    if field in _BOOL_FIELDS:
        return str(value).strip() in ("有", "あり", "True", "true", "1", "○")
    if field in _INT_FIELDS:
        try:
            return int(float(_to_number(value)))
        except (ValueError, TypeError):
            return None
    if field in _FLOAT_FIELDS:
        try:
            return float(_to_number(value))
        except (ValueError, TypeError):
            return None
    return str(value).strip()


def _parse_xlsx(file_bytes: bytes) -> tuple[dict, str]:
    """xlsx をラベルセル走査で抽出し、(抽出dict, セルダンプ文字列) を返す。"""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active

    # 全セルを (行, 列) → 値 のグリッドに展開
    grid: dict[tuple[int, int], object] = {}
    dump_lines: list[str] = []
    for row in ws.iter_rows():
        for cell in row:
            if cell.value not in (None, ""):
                grid[(cell.row, cell.column)] = cell.value
                dump_lines.append(f"{cell.coordinate}: {cell.value}")

    extracted: dict = {}
    for (r, c), value in grid.items():
        text = str(value).strip()
        if text in _LABEL_MAP:
            # ラベルの右隣を値とみなす
            neighbor = grid.get((r, c + 1))
            extracted[_LABEL_MAP[text]] = _coerce(_LABEL_MAP[text], neighbor)
        elif text in _COST_MAP:
            # 費用は真下のセル(旧様式)
            below = grid.get((r + 1, c))
            extracted[_COST_MAP[text]] = _coerce(_COST_MAP[text], below)
        elif text == "数量":
            # QF-07-03: 「不良数 / 加工数」を1セルに併記
            m = _RE_QTY.match(str(grid.get((r, c + 1)) or ""))
            if m:
                extracted["defect_count"] = int(m.group(1))
                extracted["production_count"] = int(m.group(2))
        else:
            # QF-07-03: セクション見出し(現象/要因/4M の埋め込み + 直下の本文)
            for key, field in _SECTION_TEXT.items():
                if re.match(rf"^\d+\.\s*{key}", text):
                    body = grid.get((r + 1, c))
                    if body:
                        extracted[field] = str(body).strip()
                    break
            for pat, field in ((_RE_PHENOM, "phenomenon"), (_RE_FACTOR, "factor"), (_RE_4M, "category_4m")):
                m = pat.search(text)
                if m and field not in extracted:
                    extracted[field] = m.group(1).strip()

    # None を除去
    extracted = {k: v for k, v in extracted.items() if v is not None}
    return extracted, "\n".join(dump_lines)


def _media_type(filename: str, content_type: str | None) -> str | None:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".xlsx"):
        return "xlsx"
    # フォールバックは content_type から推定
    if content_type in ("application/pdf", "image/png", "image/jpeg"):
        return content_type
    return None


@router.post("/upload", response_model=IngestResult)
async def upload(file: UploadFile, db: Session = Depends(get_db)):
    """帳票をアップロードして項目抽出する(保存はしない)。"""
    file_bytes = await file.read()
    media = _media_type(file.filename or "", file.content_type)
    warnings: list[str] = []

    if media == "xlsx":
        extracted, cell_dump = _parse_xlsx(file_bytes)
        confidence = "medium"
        # API キーがあれば Claude で正規化補正
        if llm.is_configured():
            try:
                normalized = llm.normalize_cells(cell_dump)
                for key, value in normalized.items():
                    if value is not None and value != "":
                        extracted[key] = value
                confidence = "high"
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Claude 正規化に失敗しました: {exc}")
        else:
            warnings.append(
                "AIバックエンド未設定のため、セル抽出のみで返しています(構造化補正なし)。"
            )
        return IngestResult(
            extracted=extracted,
            confidence=confidence,
            warnings=warnings,
            source_filename=file.filename or "",
        )

    if media in ("application/pdf", "image/png", "image/jpeg"):
        if not llm.is_configured():
            raise HTTPException(status_code=503, detail="AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)")
        extracted = llm.extract_from_document(file_bytes, media, file.filename or "")
        extracted = {k: v for k, v in extracted.items() if v is not None}
        return IngestResult(
            extracted=extracted,
            confidence="high",
            warnings=warnings,
            source_filename=file.filename or "",
        )

    raise HTTPException(
        status_code=400,
        detail="対応していないファイル形式です(.xlsx / .pdf / .png / .jpg)",
    )


@router.post("/confirm", response_model=ReportOut, status_code=201)
def confirm(payload: ReportCreate, db: Session = Depends(get_db)):
    """確認済みの抽出結果を保存する(POST /api/reports と同処理)。"""
    return reports_router.create_report(payload, db)
