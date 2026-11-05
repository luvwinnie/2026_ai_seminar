"""API の入出力の形（04_API設計書.md）。項目名はデータモデルの列名と同じにする。"""

from datetime import date, datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, computed_field


class HealthOut(BaseModel):
    status: str
    reports: int
    chat_backend: str  # opencode（OPENCODE_URL がある）か none


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    defect_id: str
    occurrence_date: date
    report_date: date | None
    customer: str
    discoverer: str | None
    process: str
    machine_name: str
    operator_name: str
    part_number: str
    part_name: str
    production_count: int
    defect_count: int
    defect_description: str
    good_condition: str | None
    phenomenon: str
    cause: str | None
    factor: str | None
    category_4m: str | None
    severity: str
    status: str
    countermeasure: str | None
    material_cost: float | None
    processing_cost: float | None
    outsourcing_cost: float | None
    other_cost: float | None
    total_cost: float | None
    is_recurrence: bool | None
    has_procedure: bool | None
    notes: str | None
    created_at: datetime
    updated_at: datetime | None

    @computed_field
    @property
    def defect_rate(self) -> float | None:
        """不良率＝不適合数 ÷ 加工数。保存せず、読み出すときに計算する。加工数が0なら null。"""
        if not self.production_count:
            return None
        return self.defect_count / self.production_count


class ReportList(BaseModel):
    total: int
    items: list[ReportOut]


class MasterOut(BaseModel):
    id: int
    category: str
    name: str
    sort_order: int
    is_active: bool
    usage_count: int


class MastersOut(BaseModel):
    customer: list[MasterOut]
    process: list[MasterOut]
    machine: list[MasterOut]
    operator: list[MasterOut]
    phenomenon: list[MasterOut]
    factor: list[MasterOut]


class ChatRequest(BaseModel):
    message: str
    session_id: int | None = None
    history: list | None = None  # 受け取っても使わない（履歴はサーバーが DB から読む）


class ChatAnswer(BaseModel):
    answer: str
    session_id: int


# 会話の日時は UTC で保存している（models.utcnow）。タイムゾーン付きで返し、画面が地方時に直す
UtcDatetime = Annotated[datetime, AfterValidator(lambda v: v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v)]


class ChatSessionOut(BaseModel):
    id: int
    title: str | None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    message_count: int


class ChatToolOut(BaseModel):
    name: str
    status: str
    title: str | None = None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    tools: list[ChatToolOut] | None
    thinking: str | None
    created_at: UtcDatetime


class ChatSessionDetail(BaseModel):
    session: ChatSessionOut
    messages: list[ChatMessageOut]
