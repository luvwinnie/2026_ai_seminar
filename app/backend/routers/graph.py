"""関連マップ REST — /api/graph(埋め込みの相互kNNで作る文書グラフ)。

全報告書を節、内容の近い対を縁とした無向グラフ。強い縁(相互kNN)と弱い縁を区別する。
描画はフロント(/analysis/graph)の力学レイアウトで行い、ここは作り置きの供給のみ。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services import graph as graph_service

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("")
def get_graph(db: Session = Depends(get_db)):
    g = graph_service.get_graph(db)
    # adj は検索展開用の内部構造なので返さない
    return {"mode": g["mode"], "nodes": g["nodes"], "links": g["links"]}
