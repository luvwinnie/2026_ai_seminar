"""SQLAlchemy エンジン / セッション定義。

ストアの選択(AIチャット履歴のベストプラクティス調査に基づく二段構え):
- `DATABASE_URL` が設定されていれば PostgreSQL 等の外部RDBを使う
  (Docker Compose では postgres サービスを指す。本番相当の推奨構成)。
- 未設定なら SQLite(`app/backend/data/defect_reports.db`)。
  受講者が Docker なしでもそのまま動かせるようにするための既定値。
  `DB_PATH` でファイルパスを上書き可能(テスト時は一時DBを指定する)。

どちらでもスキーマは同一(報告書・マスタ・チャット履歴)。
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# backend ディレクトリの絶対パス
BACKEND_DIR = Path(__file__).resolve().parent

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    # PostgreSQL 等(例: postgresql+psycopg://app:app@db:5432/defectreport)
    SQLALCHEMY_DATABASE_URL = DATABASE_URL
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
else:
    # SQLite(既定): ./data/defect_reports.db、env DB_PATH で上書き可
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
