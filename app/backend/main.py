"""DefectReport AI バックエンド(FastAPI)。

起動時:
- DB を初期化し、空なら data/defect_reports.csv からシード。
- Chroma 索引が空なら、バックグラウンドスレッドで構築(起動を速く保つ)。
"""
from __future__ import annotations

import csv
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import BACKEND_DIR, Base, SessionLocal, engine
from models import DefectReport
from routers import analysis, capa, chat, dashboard, digests, feedback, graph, ingest, masters, photos, reports, ui
from routers.masters import seed_masters
from services import llm, rag
from services.mcp_server import mcp_app
from routers import ontology
from routers import triage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("defectreport")

# シード元 CSV。env DATA_CSV(既定は backend からの相対パス)。
DATA_CSV = Path(os.getenv("DATA_CSV", str(BACKEND_DIR / ".." / ".." / "data" / "defect_reports.csv")))

_INT_COLS = {"production_count", "defect_count"}
_FLOAT_COLS = {
    "material_cost",
    "processing_cost",
    "outsourcing_cost",
    "other_cost",
    "total_cost",
}
_DATE_COLS = {"occurrence_date", "report_date"}
_BOOL_COLS = {"is_recurrence", "has_procedure"}


def _parse_value(col: str, raw: str):
    if raw is None or raw == "":
        return None
    if col in _INT_COLS:
        return int(float(raw))
    if col in _FLOAT_COLS:
        return float(raw)
    if col in _DATE_COLS:
        return date.fromisoformat(raw)
    if col in _BOOL_COLS:
        return str(raw).strip().lower() in ("true", "1", "有", "yes")
    return raw


def seed_from_csv() -> int:
    """テーブルが空なら CSV からシードする。CSV が無ければ警告して継続。"""
    db = SessionLocal()
    try:
        if db.query(DefectReport).count() > 0:
            return 0
        if not DATA_CSV.exists():
            logger.warning("シード用CSVが見つかりません: %s(空のまま起動します)", DATA_CSV)
            return 0

        inserted = 0
        with open(DATA_CSV, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data = {col: _parse_value(col, val) for col, val in row.items()}
                db.add(DefectReport(**data))
                inserted += 1
        db.commit()
        logger.info("CSV から %d 件シードしました", inserted)
        return inserted
    finally:
        db.close()


def _seed_masters():
    """マスタを投入する(空のときのみ)。"""
    db = SessionLocal()
    try:
        count = seed_masters(db)
        if count:
            logger.info("マスタを %d 件シードしました", count)
    finally:
        db.close()


def _build_index_background():
    """Chroma 索引をバックグラウンドで構築する。"""
    db = SessionLocal()
    try:
        count = rag.index_all(db)
        logger.info("Chroma 索引: %d 件(mode=%s)", count, rag.get_mode())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chroma 索引構築に失敗: %s", exc)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """起動時: DB初期化・シード・索引構築(バックグラウンド)+ MCP アプリの lifespan。"""
    Base.metadata.create_all(bind=engine)
    seed_from_csv()
    # マスタは報告書シード後に投入(DISTINCT 値を拾うため)
    _seed_masters()
    # 索引構築は起動をブロックしないようバックグラウンドで実行
    threading.Thread(target=_build_index_background, daemon=True).start()
    # FastMCP(Streamable HTTP)はセッションマネージャの起動が必要
    async with mcp_app.lifespan(app):
        yield


app = FastAPI(title="DefectReport AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reports.router)
app.include_router(ingest.router)
app.include_router(dashboard.router)
app.include_router(analysis.router)
app.include_router(chat.router)
app.include_router(masters.router)
app.include_router(ui.router)
app.include_router(digests.router)
app.include_router(capa.router)
app.include_router(photos.router)
app.include_router(graph.router)
app.include_router(feedback.router)
app.include_router(ontology.router)
app.include_router(triage.router)

# MCP サーバー(OpenCode 等から http://<host>:8000/mcp/ で接続)
app.mount("/mcp", mcp_app)


@app.get("/health")
def health():
    db = SessionLocal()
    try:
        count = db.query(DefectReport).count()
    finally:
        db.close()
    return {
        "status": "ok",
        "reports": count,
        "anthropic_configured": llm.is_configured(),
        "chat_backend": chat.chat_backend(),
        "vector_search": rag.get_mode(),
    }
