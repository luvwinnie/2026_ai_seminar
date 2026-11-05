"""RAG 用ベクトル索引(Chroma + multilingual-e5-small)。

sentence-transformers が利用不可の環境では SQLite の LIKE 検索にフォールバックし、
結果に `search_mode: "keyword"` を明示する(docs/03 §3)。
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from database import BACKEND_DIR
from models import DefectReport

logger = logging.getLogger(__name__)

# 埋め込みを使うかどうか。EMBEDDINGS=off でキーワード検索に固定できる(Docker軽量化・テスト用)。
_EMBEDDINGS_ENABLED = os.getenv("EMBEDDINGS", "on").lower() != "off"

CHROMA_PATH = Path(os.getenv("CHROMA_PATH", str(BACKEND_DIR / "data" / "chroma")))
COLLECTION_NAME = "defect_reports"
MODEL_NAME = "intfloat/multilingual-e5-small"

_lock = threading.Lock()
_model = None  # sentence-transformers モデル(遅延ロード)
_model_failed = False  # ロード失敗を記録し、以降はキーワード検索に落とす
_client = None
_collection = None


def _get_model():
    """e5 モデルを遅延ロードする。失敗したら None を返しキーワード検索へフォールバック。"""
    global _model, _model_failed
    if not _EMBEDDINGS_ENABLED or _model_failed:
        return None
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer  # 遅延 import

            _model = SentenceTransformer(MODEL_NAME)
        except Exception:
            _model_failed = True
            _model = None
    return _model


def _get_collection():
    """Chroma コレクションを取得(cosine 空間)。"""
    global _client, _collection
    if _collection is not None:
        return _collection
    with _lock:
        if _collection is not None:
            return _collection
        import chromadb  # 遅延 import

        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def get_mode() -> str:
    """現在の検索モード("e5" または "keyword")。"""
    return "e5" if _get_model() is not None else "keyword"


def _document_text(r: DefectReport) -> str:
    """埋め込み対象のドキュメント文(docs/03 §3)。"""
    return f"{r.defect_description or ''}\n原因: {r.cause or ''}\n対策: {r.countermeasure or ''}"


def _metadata(r: DefectReport) -> dict:
    """Chroma メタデータ(None は空文字に正規化)。"""
    return {
        "defect_id": r.defect_id or "",
        "occurrence_date": r.occurrence_date.isoformat() if r.occurrence_date else "",
        "machine_name": r.machine_name or "",
        "process": r.process or "",
        "phenomenon": r.phenomenon or "",
        "severity": r.severity or "",
        "part_name": r.part_name or "",
        "customer": r.customer or "",
    }


def _encode_passages(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    prefixed = [f"passage: {t}" for t in texts]
    return model.encode(prefixed, normalize_embeddings=True).tolist()


def _encode_query(text: str) -> list[float]:
    model = _get_model()
    return model.encode(f"query: {text}", normalize_embeddings=True).tolist()


def upsert(report: DefectReport) -> None:
    """1件を索引に upsert する(埋め込み無効時はベクトル側のみスキップ)。"""
    from services import hybrid

    hybrid.invalidate()  # BM25 索引は次回検索時に再構築
    from services import graph as _graph_mod

    _graph_mod.invalidate()
    if _get_model() is None:
        return
    try:
        col = _get_collection()
        emb = _encode_passages([_document_text(report)])
        col.upsert(
            ids=[report.defect_id],
            embeddings=emb,
            documents=[_document_text(report)],
            metadatas=[_metadata(report)],
        )
    except Exception:
        # 索引更新の失敗は検索フォールバックで吸収できるため握りつぶす
        pass


def delete(defect_id: str) -> None:
    """索引から削除する。"""
    from services import graph as _graph_mod
    from services import hybrid

    hybrid.invalidate()
    _graph_mod.invalidate()
    if _get_model() is None:
        return
    try:
        _get_collection().delete(ids=[defect_id])
    except Exception:
        pass


def index_all(db: Session, force: bool = False) -> int:
    """全報告書を索引化する。既に件数があれば何もしない(force=True で再構築)。"""
    if _get_model() is None:
        return 0
    col = _get_collection()
    if not force and col.count() > 0:
        return col.count()

    rows = db.query(DefectReport).all()
    if not rows:
        return 0

    # バッチで埋め込みを計算して upsert
    batch = 32
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        docs = [_document_text(r) for r in chunk]
        col.upsert(
            ids=[r.defect_id for r in chunk],
            embeddings=_encode_passages(docs),
            documents=docs,
            metadatas=[_metadata(r) for r in chunk],
        )
    return col.count()


def _snippet(text: str, limit: int = 140) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text[:limit]


def _dense_search(query: str, n_results: int = 30) -> list[dict]:
    """e5 ベクトル検索の順位リスト([{defect_id, score}...])。使えなければ空リスト。"""
    if _get_model() is None:
        return []
    try:
        col = _get_collection()
        if col.count() == 0:
            return []
        res = col.query(query_embeddings=[_encode_query(query)], n_results=n_results)
        ids = res.get("ids", [[]])[0]
        dists = res.get("distances", [[]])[0]
        return [
            {"defect_id": did, "score": round(1.0 - float(dists[i]), 4)}
            for i, did in enumerate(ids)
        ]
    except Exception:
        return []


def search(db: Session, query: str, top_k: int = 5) -> list[dict]:
    """上位 top_k 件を検索する(ハイブリッド: 形態素BM25 + e5 の RRF 融合)。

    - e5 が使えれば BM25 と融合(search_mode="hybrid")
    - e5 が使えなくても BM25 単独で動く(search_mode="bm25")
    - それも失敗した場合のみ SQLite LIKE のキーワード検索(search_mode="keyword")
    同義語展開・ファセット補正は services/hybrid.py 側で行う(docs/09 優先度A)。
    """
    dense_hits = _dense_search(query)
    try:
        from services import decisions, hybrid  # 遅延 import(循環回避)

        if decisions.enabled("rerank"):
            # ① 判断モデルで並べ直す(2026-10-18)。候補を多めに取り、「質問に当てはまる確率」の順に上位 top_k 件
            n = decisions.DECISION_PROFILE["rerank"]["candidates"]
            cand = hybrid.fuse(db, query, dense_hits, top_k=max(n, top_k))
            if cand:
                try:
                    rows = {r.defect_id: r for r in db.query(DefectReport).filter(
                        DefectReport.defect_id.in_([c["defect_id"] for c in cand])).all()}
                    ranked, info = decisions.rerank(query, cand, rows, top_k=top_k)
                    for it in ranked:
                        it["search_mode"] = (it.get("search_mode") or "hybrid") + "+rerank"
                        it["rerank_abstain"] = info["abstain"]
                    return ranked
                except Exception as exc:  # noqa: BLE001 — 判断モデルが使えなくても検索は続ける
                    logger.warning("rerank failed, fallback to hybrid: %s", exc)
                    return cand[:top_k]
        out = hybrid.fuse(db, query, dense_hits, top_k=top_k)
        if out:
            return out
    except Exception:
        # ハイブリッド側の不具合は従来経路で吸収する
        pass

    return _keyword_search(db, query, top_k)


def _keyword_search(db: Session, query: str, top_k: int) -> list[dict]:
    """SQLite LIKE によるキーワード検索フォールバック。"""
    from sqlalchemy import or_

    terms = [t for t in query.split() if t] or [query]
    conditions = []
    for t in terms:
        like = f"%{t}%"
        conditions.append(DefectReport.defect_description.like(like))
        conditions.append(DefectReport.cause.like(like))
        conditions.append(DefectReport.countermeasure.like(like))
        conditions.append(DefectReport.part_name.like(like))
        conditions.append(DefectReport.phenomenon.like(like))

    rows = db.query(DefectReport).filter(or_(*conditions)).all()

    # 出現語数で簡易スコアリング
    def score(r: DefectReport) -> int:
        blob = " ".join(
            filter(
                None,
                [r.defect_description, r.cause, r.countermeasure, r.part_name, r.phenomenon],
            )
        )
        return sum(blob.count(t) for t in terms)

    rows.sort(key=score, reverse=True)
    out = []
    for r in rows[:top_k]:
        out.append(
            {
                "defect_id": r.defect_id,
                "part_name": r.part_name,
                "machine_name": r.machine_name,
                "process": r.process,
                "phenomenon": r.phenomenon,
                "snippet": _snippet(_document_text(r)),
                "score": float(score(r)),
                "search_mode": "keyword",
            }
        )
    return out
