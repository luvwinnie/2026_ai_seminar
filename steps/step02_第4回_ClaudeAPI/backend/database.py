"""SQLAlchemy エンジン / セッション定義。

正本ストアは SQLite(`app/backend/data/defect_reports.db`)。
環境変数 `DB_PATH` でファイルパスを上書き可能(テスト時は一時DBを指定する)。
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# backend ディレクトリの絶対パス
BACKEND_DIR = Path(__file__).resolve().parent

# DB ファイルパス(既定は ./data/defect_reports.db、env で上書き可)
_default_db = BACKEND_DIR / "data" / "defect_reports.db"
DB_PATH = Path(os.getenv("DB_PATH", str(_default_db)))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # SQLite を FastAPI の複数スレッドから使うため
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依存性: リクエストごとに DB セッションを払い出す。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
