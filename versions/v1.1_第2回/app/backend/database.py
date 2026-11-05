"""DB への接続を作る（03_データモデル設計書.md §1）。接続はこのファイルの1か所で作る。"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent.parent

# 既定のパスはこのファイルの場所から決める（どのフォルダから起動しても同じになる）
DB_PATH = Path(os.environ.get("DB_PATH", BACKEND_DIR / "data" / "defect_reports.db"))
DATA_CSV = Path(os.environ.get("DATA_CSV", REPO_DIR / "data" / "defect_reports.csv"))
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    engine = create_engine(DATABASE_URL)
else:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    # SQLite は FastAPI の複数のスレッドから使うため
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
