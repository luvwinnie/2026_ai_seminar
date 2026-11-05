"""数量の決まり 0 ≦ 不適合数 ≦ 加工数（07_試験・運用仕様書.md §2.4 AC-v21-06）。

構造化出力の検査は第3回では作らない（後の回）。第3回は、DB に入れた110件が決まりを満たすことだけを確かめる。
"""

from sqlalchemy import func, or_, select

from database import SessionLocal
from models import DefectReport


def test_AC_v21_06_all_reports_satisfy_quantity_rule(client):
    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(DefectReport))
        violations = db.scalar(
            select(func.count()).select_from(DefectReport).where(or_(
                DefectReport.defect_count < 0,
                DefectReport.defect_count > DefectReport.production_count,
            ))
        )
    assert total == 110
    assert violations == 0
