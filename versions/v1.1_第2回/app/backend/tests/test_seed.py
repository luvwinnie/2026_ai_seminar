import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base
from seed import convert_row, seed_masters, seed_reports


@pytest.mark.parametrize(
    "raw, expected",
    [("True", True), ("true", True), ("1", True), ("有", True), ("yes", True),
     ("False", False), ("0", False), ("無", False)],
)
def test_AC_v10_07_bool_values(raw, expected):
    assert convert_row({"is_recurrence": raw})["is_recurrence"] is expected


def test_AC_v10_07_blank_values():
    row = convert_row({"category_4m": "", "notes": "", "has_procedure": "", "total_cost": "60581.0"})
    assert row["category_4m"] is None
    assert row["notes"] is None
    assert "has_procedure" not in row  # 空の真偽は列の既定に任せる
    assert row["total_cost"] == 60581.0


def test_AC_v10_01_missing_csv_starts_empty(tmp_path, caplog):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db, caplog.at_level(logging.WARNING):
        assert seed_reports(db, Path(tmp_path) / "none.csv") == 0
        assert seed_masters(db) == 0
    assert "模擬データが見つかりません" in caplog.text
