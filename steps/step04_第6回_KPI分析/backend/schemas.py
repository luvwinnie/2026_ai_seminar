"""Pydantic スキーマ定義。

API のリクエスト/レスポンス形状は docs/03・docs/04 に一致させる。
ReportOut は全カラム + 派生値 `defect_rate` を返す。
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, computed_field


class ReportBase(BaseModel):
    """報告書の共通フィールド(作成・更新で使い回す)。"""

    occurrence_date: date | None = None
    report_date: date | None = None
    customer: str | None = None
    discoverer: str | None = None
    process: str | None = None
    machine_name: str | None = None
    operator_name: str | None = None
    part_number: str | None = None
    part_name: str | None = None
    production_count: int | None = None
    defect_count: int | None = None
    defect_description: str | None = None
    good_condition: str | None = None
    phenomenon: str | None = None
    cause: str | None = None
    factor: str | None = None
    category_4m: str | None = None
    severity: str | None = None
    status: str | None = None
    countermeasure: str | None = None
    material_cost: float | None = None
    processing_cost: float | None = None
    outsourcing_cost: float | None = None
    other_cost: float | None = None
    total_cost: float | None = None
    is_recurrence: bool | None = None
    has_procedure: bool | None = None
    notes: str | None = None
    ai_improvement: str | None = None


class ReportCreate(ReportBase):
    """新規作成。defect_id 未指定ならサーバ側で採番する。

    必須項目(docs/03)は作成時に検証する。
    """

    defect_id: str | None = None
    occurrence_date: date
    customer: str
    process: str
    machine_name: str
    operator_name: str
    part_number: str
    part_name: str
    production_count: int
    defect_count: int
    defect_description: str
    phenomenon: str
    severity: str
    status: str = "open"


class ReportUpdate(ReportBase):
    """部分更新。渡されたフィールドのみ反映する。"""


class ReportOut(ReportBase):
    """詳細レスポンス。全カラム + defect_rate。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    defect_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def defect_rate(self) -> float | None:
        """不適合数 / 加工数(0除算時は None)。"""
        if not self.production_count:
            return None
        return self.defect_count / self.production_count


class ReportList(BaseModel):
    """一覧レスポンス。"""

    total: int
    items: list[ReportOut]


# --- 取り込み(ingest) ---


class IngestResult(BaseModel):
    """帳票取り込み結果(保存はしない・確認画面用)。"""

    extracted: dict
    confidence: str  # high / medium / low
    warnings: list[str] = []
    source_filename: str


# --- チャット ---


class ChatMessage(BaseModel):
    role: str  # user / assistant
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatSource(BaseModel):
    defect_id: str
    part_name: str | None = None
    phenomenon: str | None = None
    snippet: str
    score: float


class ChatResponse(BaseModel):
    """非ストリーミング版チャットの応答(テスト用)。"""

    answer: str
    sources: list[ChatSource] = []
