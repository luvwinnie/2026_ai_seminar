"""表の定義（03_データモデル設計書.md §4・§6）。"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

# 費用は DB では Numeric、API では数値（小数）で返すため float で読み出す
Money = Numeric(14, 2, asdecimal=False)


class DefectReport(Base):
    __tablename__ = "defect_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    defect_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    occurrence_date: Mapped[date] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)
    customer: Mapped[str] = mapped_column(String(100))
    discoverer: Mapped[str | None] = mapped_column(String(50))
    process: Mapped[str] = mapped_column(String(50))
    machine_name: Mapped[str] = mapped_column(String(100))
    operator_name: Mapped[str] = mapped_column(String(50))
    part_number: Mapped[str] = mapped_column(String(50))
    part_name: Mapped[str] = mapped_column(String(100))
    production_count: Mapped[int] = mapped_column(Integer)
    defect_count: Mapped[int] = mapped_column(Integer)
    defect_description: Mapped[str] = mapped_column(Text)
    good_condition: Mapped[str | None] = mapped_column(Text)
    phenomenon: Mapped[str] = mapped_column(String(50))
    cause: Mapped[str | None] = mapped_column(Text)
    factor: Mapped[str | None] = mapped_column(String(50))
    category_4m: Mapped[str | None] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open")
    countermeasure: Mapped[str | None] = mapped_column(Text)
    material_cost: Mapped[float | None] = mapped_column(Money)
    processing_cost: Mapped[float | None] = mapped_column(Money)
    outsourcing_cost: Mapped[float | None] = mapped_column(Money)
    other_cost: Mapped[float | None] = mapped_column(Money)
    total_cost: Mapped[float | None] = mapped_column(Money)
    is_recurrence: Mapped[bool | None] = mapped_column(Boolean, default=False)
    has_procedure: Mapped[bool | None] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class MasterItem(Base):
    __tablename__ = "masters"
    __table_args__ = (UniqueConstraint("category", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
