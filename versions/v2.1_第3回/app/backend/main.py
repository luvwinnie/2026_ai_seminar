import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import models  # noqa: F401  表の定義を Base に登録する
from database import DATA_CSV, Base, SessionLocal, engine
from routers import chat, health, masters, reports
from seed import seed_masters, seed_reports
from services.mcp_server import mcp

logging.basicConfig(level=logging.INFO)

# MCP サーバー（04_API設計書.md §8.1）。URL は /mcp/（末尾の / が要る）
mcp_app = mcp.http_app(path="/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時の処理（03_データモデル設計書.md §1.2）
    Base.metadata.create_all(engine)  # 無い表を作る
    with SessionLocal() as db:
        seed_reports(db, DATA_CSV)  # 報告書が0件なら CSV を入れる
        seed_masters(db)  # masters が空なら作る
    async with mcp_app.lifespan(app):  # MCP の受付を動かす
        yield


app = FastAPI(title="DefectReport AI", lifespan=lifespan)
app.include_router(health.router)
app.include_router(reports.router)
app.include_router(masters.router)
app.include_router(chat.router)
app.mount("/mcp", mcp_app)
