"""不適合報告書テーブル定義(docs/03 データモデル設計書に準拠)。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.sql import func

from database import Base


class DefectReport(Base):
    """不適合報告書の正本。API の JSON フィールド名もこの属性名に一致させる。"""

    __tablename__ = "defect_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    defect_id = Column(String, unique=True, nullable=False, index=True)  # KZ25-0001 形式

    occurrence_date = Column(Date, nullable=False)  # 発生日
    report_date = Column(Date)  # 報告日

    customer = Column(String, nullable=False)  # 客先
    discoverer = Column(String)  # 発見者名
    process = Column(String, nullable=False)  # 発生工程
    machine_name = Column(String, nullable=False)  # 使用機械
    operator_name = Column(String, nullable=False)  # 作業者名

    part_number = Column(String, nullable=False)  # 部品番号
    part_name = Column(String, nullable=False)  # 部品名称
    production_count = Column(Integer, nullable=False)  # 加工数
    defect_count = Column(Integer, nullable=False)  # 不適合数

    defect_description = Column(Text, nullable=False)  # 不具合内容
    good_condition = Column(Text)  # 良品状態
    phenomenon = Column(String, nullable=False)  # 現象分類
    cause = Column(Text)  # 原因
    factor = Column(String)  # 要因
    category_4m = Column(String)  # 4M分類(Man/Machine/Material/Method)

    severity = Column(String, nullable=False)  # critical/high/medium/low
    status = Column(String, nullable=False, default="open")  # open/in_progress/completed
    countermeasure = Column(Text)  # 対策

    material_cost = Column(Numeric)  # 材料費
    processing_cost = Column(Numeric)  # 社内加工費
    outsourcing_cost = Column(Numeric)  # 外注加工費
    other_cost = Column(Numeric)  # その他費用
    total_cost = Column(Numeric)  # 合計損失

    is_recurrence = Column(Boolean, default=False)  # 再発フラグ
    has_procedure = Column(Boolean, default=True)  # 手順書有無
    notes = Column(Text)  # 備考
    ai_improvement = Column(Text)  # AI生成の改善提案

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    @property
    def defect_rate(self) -> float | None:
        """派生値: 不適合数 / 加工数(0除算時は None)。"""
        if not self.production_count:
            return None
        return self.defect_count / self.production_count
