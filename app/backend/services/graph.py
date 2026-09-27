"""報告書どうしの「近さ」のグラフ(文書グラフ / GraphRAG の考え方)。

2つの用途:
  1. 関連マップ画面(/analysis/graph): 全報告書を節、内容の近い対を縁として可視化する。
     「どの不良とどの不良が同じことを言っているか」の地図(Obsidian の Graph View 相当)。
  2. 検索のグラフ展開: 検索ヒットの近傍文書へスコアを減衰伝播(α)して取りこぼしを拾う。
     引用や近さのグラフで近傍をたどると、Recall(取りこぼしの少なさ)が上がりやすい。

作り方(一般的な文書グラフの作り方):
  - 文書ベクトルは Chroma に保存済みの埋め込みを再利用(モデルを呼び直さない)。
    埋め込み未導入時はキーワード(トークン集合の Jaccard)で代替する。
  - 各節から上位 K 本だけ残す。**両方から選ばれた対(相互kNN)を強い縁**、
    片方向のみは弱い縁とする(「片思いはたまたま似ていることが多い」)。
  - プロセス内キャッシュ。報告書の増減で自動再構築(rag.upsert/delete → invalidate)。
"""
from __future__ import annotations

import math
import threading

from sqlalchemy.orm import Session

from models import DefectReport

_K = 5            # 各節が張る候補縁の本数
_MIN_SIM = 0.80   # 埋め込みコサインの下限(それ未満は縁にしない)
_MIN_JACC = 0.18  # フォールバック(Jaccard)の下限
_ALPHA = 0.25     # 検索グラフ展開の減衰率(控えめに伝播させ、近傍が上位を占めすぎないようにする)

_lock = threading.Lock()
_graph: dict | None = None  # {"nodes": [...], "links": [...], "adj": {id: [(id, w, mutual)]}}
_dirty = True


def invalidate() -> None:
    global _dirty
    _dirty = True


def _embeddings() -> dict[str, list[float]] | None:
    """Chroma から保存済み埋め込みを取り出す。無ければ None(フォールバックへ)。"""
    try:
        from services import rag

        col = rag._get_collection()
        if col is None:
            return None
        got = col.get(include=["embeddings"])
        ids = got.get("ids") or []
        embs = got.get("embeddings")
        if embs is None or len(ids) == 0:
            return None
        return {i: list(map(float, e)) for i, e in zip(ids, embs)}
    except Exception:
        return None


def _cos(a: list[float], b: list[float]) -> float:
    # e5 は正規化済みだが、防御的に分母を計算する
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def _build(db: Session) -> dict:
    rows = db.query(DefectReport).all()
    ids = [r.defect_id for r in rows]
    by_id = {r.defect_id: r for r in rows}

    emb = _embeddings()
    sims: dict[str, list[tuple[str, float]]] = {}
    if emb and all(i in emb for i in ids):
        for i in ids:
            cand = [(j, _cos(emb[i], emb[j])) for j in ids if j != i]
            cand = [(j, s) for j, s in cand if s >= _MIN_SIM]
            cand.sort(key=lambda t: -t[1])
            sims[i] = cand[:_K]
        mode = "embedding"
    else:
        # フォールバック: トークン集合の Jaccard(hybrid と同じトークナイザ)
        from services.hybrid import tokenize

        toks = {
            r.defect_id: set(
                tokenize(" ".join(filter(None, [r.defect_description, r.cause, r.countermeasure, r.part_name])))
            )
            for r in rows
        }
        for i in ids:
            cand = []
            for j in ids:
                if j == i:
                    continue
                inter = len(toks[i] & toks[j])
                union = len(toks[i] | toks[j]) or 1
                s = inter / union
                if s >= _MIN_JACC:
                    cand.append((j, s))
            cand.sort(key=lambda t: -t[1])
            sims[i] = cand[:_K]
        mode = "jaccard"

    chosen = {i: {j for j, _ in sims[i]} for i in ids}
    links = []
    seen = set()
    adj: dict[str, list[tuple[str, float, bool]]] = {i: [] for i in ids}
    for i in ids:
        for j, s in sims[i]:
            key = tuple(sorted((i, j)))
            if key in seen:
                continue
            seen.add(key)
            mutual = i in chosen.get(j, set())
            links.append({"s": key[0], "t": key[1], "w": round(s, 4), "m": mutual})
            adj[i].append((j, s, mutual))
            adj[j].append((i, s, mutual))

    nodes = []
    deg = {i: 0 for i in ids}
    for l_ in links:
        deg[l_["s"]] += 1
        deg[l_["t"]] += 1
    for r in rows:
        nodes.append(
            {
                "id": r.defect_id,
                "part": r.part_name,
                "phenomenon": r.phenomenon,
                "machine": r.machine_name,
                "severity": r.severity,
                "cost": float(r.total_cost or 0),
                "d": deg[r.defect_id],
            }
        )
    return {"mode": mode, "nodes": nodes, "links": links, "adj": adj, "n": len(ids)}


def get_graph(db: Session) -> dict:
    global _graph, _dirty
    n = db.query(DefectReport).count()
    if _graph is None or _dirty or _graph["n"] != n:
        with _lock:
            if _graph is None or _dirty or _graph["n"] != n:
                _graph = _build(db)
                _dirty = False
    return _graph


def expand_scores(db: Session, scores: dict[str, float], alpha: float = _ALPHA) -> dict[str, float]:
    """検索スコアをグラフ近傍へ1ホップ減衰伝播する(強い縁のみ)。

    ヒット済み文書は下げない(max で合成)。未ヒットの近傍だけが浮上する。
    """
    if not scores or alpha <= 0:
        return scores
    g = get_graph(db)
    out = dict(scores)
    for did, sc in scores.items():
        for j, w, mutual in g["adj"].get(did, []):
            if not mutual:
                continue
            prop = sc * alpha * w
            if prop > out.get(j, 0.0):
                out[j] = prop
    return out
