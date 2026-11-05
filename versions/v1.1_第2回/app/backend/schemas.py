"""API の入出力の形（04_API設計書.md）。項目名はデータモデルの列名と同じにする。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, computed_field


class HealthOut(BaseModel):
    status: str
    reports: int


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
