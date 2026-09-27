"""ハイブリッド検索 — 形態素BM25 + 密ベクトルの RRF 融合 + 同義語展開 + ファセット層。

密ベクトルだけより、キーワード(BM25)と組み合わせるほうが検索順位が良くなりやすい、という一般的な知見に基づく構成
(docs/09_強化候補_RAG事例の分析.md 優先度A)。

- トークン化: SudachiPy(Mode A)があれば形態素、無ければ文字バイグラム+英数語に自動フォールバック
  (sentence-transformers と同じ「重い依存は任意」方針)
- 同義語展開: services/synonyms.json の製造用語グループでクエリを展開(表記揺れ対策)
- ファセット層: 機械名/工程/重大度/4M を LLM を使わず決定論的に突き合わせる。
  クエリで明示された属性と不一致の文書を減点、一致を軽く加点。属性が読めない文書は中立
- 融合: BM25 と密ベクトルの順位を RRF(k=60)で合成

索引はプロセス内キャッシュ。報告書の作成/更新/削除時は rag.upsert/delete 経由で
invalidate() が呼ばれ、次回検索時に再構築される(数百件規模なので全再構築で十分)。
"""
from __future__ import annotations

import json
import math
import re
import threading
import unicodedata
from collections import Counter
from pathlib import Path

from sqlalchemy.orm import Session

from models import DefectReport

_BASE = Path(__file__).parent

# ---------------------------------------------------------------------------
# トークン化(SudachiPy → 文字バイグラムフォールバック)
# ---------------------------------------------------------------------------
_sudachi = None
_sudachi_failed = False
_lock = threading.Lock()  # Sudachi 初期化用
_index_lock = threading.Lock()  # BM25 索引構築用(_lock とは分離。同一ロックだと
# _get_index → tokenize → _get_sudachi で再取得となりデッドロックする)

_ASCII_WORD = re.compile(r"[a-z0-9]+")
_JA_CHAR = re.compile(r"[ぁ-んァ-ヶ一-龠々ー]")


def _get_sudachi():
    global _sudachi, _sudachi_failed
    if _sudachi is not None or _sudachi_failed:
        return _sudachi
    with _lock:
        if _sudachi is not None or _sudachi_failed:
            return _sudachi
        try:
            from sudachipy import dictionary, tokenizer  # 遅延 import(任意依存)

            obj = dictionary.Dictionary().create()
            _sudachi = (obj, tokenizer.Tokenizer.SplitMode.A)
        except Exception:
            _sudachi_failed = True
    return _sudachi


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def tokenize(text: str) -> list[str]:
    """検索用トークン列。Sudachi があれば短単位の形態素、無ければ日本語バイグラム+英数語。"""
    text = _normalize(text)
    sd = _get_sudachi()
    if sd is not None:
        obj, mode = sd
        try:
            return [m.surface() for m in obj.tokenize(text, mode) if m.surface().strip()]
        except Exception:
            pass
    tokens = _ASCII_WORD.findall(text)
    ja = "".join(_JA_CHAR.findall(text))
    tokens += [ja[i : i + 2] for i in range(len(ja) - 1)]
    if len(ja) == 1:
        tokens.append(ja)
    return tokens


# ---------------------------------------------------------------------------
# 同義語展開(クエリ側のみ)
# ---------------------------------------------------------------------------
_syn_groups: list[list[str]] | None = None


def _load_synonyms() -> list[list[str]]:
    global _syn_groups
    if _syn_groups is None:
        groups: list[list[str]] = []
        # 手書き辞書 + コーパス駆動の自動生成辞書(scripts/build_synonyms.py --apply)
        for fname in ("synonyms.json", "synonyms_generated.json"):
            try:
                data = json.loads((_BASE / fname).read_text(encoding="utf-8"))
                groups += [[_normalize(w) for w in g] for g in data.get("groups", [])]
            except Exception:
                pass  # 生成辞書は任意(無くても動く)
        _syn_groups = groups
    return _syn_groups


def expand_query(query: str) -> str:
    """クエリ文字列に、含まれる用語の同義語を追記して返す(部分文字列一致)。"""
    qn = _normalize(query)
    extra: list[str] = []
    for group in _load_synonyms():
        if any(w in qn for w in group):
            extra += [w for w in group if w not in qn]
    return query + (" " + " ".join(extra) if extra else "")


# ---------------------------------------------------------------------------
# ファセット層(決定論的な属性突き合わせ。LLM 不使用)
# ---------------------------------------------------------------------------
_SEVERITIES = ("重大", "軽微", "中")
_4M = {
    "man": re.compile(r"\bman\b|人的|作業者要因|ヒューマンエラー"),
    "machine": re.compile(r"\bmachine\b|設備要因|機械要因"),
    "material": re.compile(r"\bmaterial\b|材料要因"),
    "method": re.compile(r"\bmethod\b|方法要因|手順要因"),
}
_FACET_MISMATCH = 0.55  # 不一致ペナルティ(乗算)
_FACET_MATCH = 1.15  # 一致ボーナス(控えめ)


def extract_query_facets(query: str, machines: list[str], processes: list[str]) -> dict:
    """クエリに明示された属性を抽出する。読み取れなければ空(中立)。"""
    qn = _normalize(query)
    facets: dict = {}
    hits = [m for m in machines if len(m) >= 2 and _normalize(m) in qn]
    if hits:
        facets["machine"] = max(hits, key=len)  # 「NC旋盤A」優先(最長一致)
    hits = [p for p in processes if len(p) >= 2 and _normalize(p) in qn]
    if hits:
        facets["process"] = max(hits, key=len)
    for s in _SEVERITIES:
        if f"重大度{s}" in qn or f"{s}な不良" in qn or (s == "重大" and "重大" in qn):
            facets["severity"] = s
            break
    for name, pat in _4M.items():
        if pat.search(qn):
            facets["category_4m"] = name.capitalize()
            break
    return facets


def facet_multiplier(facets: dict, row: DefectReport) -> float:
    """属性の一致/不一致に応じた係数。文書側の属性が空なら中立(1.0)。"""
    mult = 1.0
    checks = (
        (facets.get("machine"), row.machine_name),
        (facets.get("process"), row.process),
        (facets.get("severity"), row.severity),
        (facets.get("category_4m"), row.category_4m),
    )
    for want, have in checks:
        if not want or not have:
            continue
        if _normalize(want) == _normalize(have) or _normalize(want) in _normalize(have):
            mult *= _FACET_MATCH
        else:
            mult *= _FACET_MISMATCH
    return mult


# ---------------------------------------------------------------------------
# BM25 索引(プロセス内・全再構築方式)
# ---------------------------------------------------------------------------
_K1 = 1.4
_B = 0.75


class _Index:
    def __init__(self, rows: list[DefectReport]):
        self.ids: list[str] = []
        self.tfs: list[Counter] = []
        self.lens: list[int] = []
        self.df: Counter = Counter()
        self.machines: set[str] = set()
        self.processes: set[str] = set()
        for r in rows:
            text = " ".join(
                filter(
                    None,
                    [r.defect_description, r.cause, r.countermeasure,
                     r.part_name, r.phenomenon, r.machine_name, r.process],
                )
            )
            toks = tokenize(text)
            tf = Counter(toks)
            self.ids.append(r.defect_id)
            self.tfs.append(tf)
            self.lens.append(len(toks))
            for t in tf:
                self.df[t] += 1
            if r.machine_name:
                self.machines.add(r.machine_name)
            if r.process:
                self.processes.add(r.process)
        self.n = len(self.ids)
        self.avg_len = (sum(self.lens) / self.n) if self.n else 0.0

    def bm25(self, qtokens: list[str], top_n: int = 50) -> list[tuple[str, float]]:
        if not self.n:
            return []
        scores = [0.0] * self.n
        for t in set(qtokens):
            df = self.df.get(t)
            if not df:
                continue
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self.tfs):
                f = tf.get(t)
                if not f:
                    continue
                denom = f + _K1 * (1 - _B + _B * self.lens[i] / (self.avg_len or 1))
                scores[i] += idf * f * (_K1 + 1) / denom
        order = sorted(range(self.n), key=lambda i: scores[i], reverse=True)
        return [(self.ids[i], scores[i]) for i in order[:top_n] if scores[i] > 0]


_index: _Index | None = None
_dirty = True


def invalidate() -> None:
    """報告書の作成/更新/削除時に呼ぶ。次回検索時に索引を再構築する。"""
    global _dirty
    _dirty = True


def _get_index(db: Session) -> _Index:
    global _index, _dirty
    rows_count = db.query(DefectReport).count()
    if _index is None or _dirty or _index.n != rows_count:
        with _index_lock:
            if _index is None or _dirty or _index.n != rows_count:
                rows = db.query(DefectReport).all()
                _index = _Index(rows)
                _dirty = False
    return _index


# ---------------------------------------------------------------------------
# RRF 融合 + 出力整形
# ---------------------------------------------------------------------------
_RRF_K = 60


def _snippet(text: str, limit: int = 140) -> str:
    return (text or "").replace("\n", " ").strip()[:limit]


def fuse(db: Session, query: str, dense_hits: list[dict], top_k: int = 5) -> list[dict]:
    """BM25 と密ベクトル結果を RRF で融合し、ファセット補正して上位 top_k を返す。

    dense_hits: rag._dense_search の結果([{defect_id, score}...]、無ければ空リスト)。
    """
    idx = _get_index(db)
    qtokens = tokenize(expand_query(query))
    bm25_hits = idx.bm25(qtokens, top_n=50)

    scores: dict[str, float] = {}
    for rank, (defect_id, _s) in enumerate(bm25_hits):
        scores[defect_id] = scores.get(defect_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
    for rank, hit in enumerate(dense_hits):
        did = hit["defect_id"]
        scores[did] = scores.get(did, 0.0) + 1.0 / (_RRF_K + rank + 1)
    if not scores:
        return []

    # ファセット補正(行データが必要なのでまとめて取得)
    rows = {
        r.defect_id: r
        for r in db.query(DefectReport).filter(DefectReport.defect_id.in_(list(scores))).all()
    }
    facets = extract_query_facets(query, sorted(idx.machines), sorted(idx.processes))
    if facets:
        for did in list(scores):
            row = rows.get(did)
            if row is not None:
                scores[did] *= facet_multiplier(facets, row)

    # グラフ展開: ヒットの近傍文書へスコアを減衰伝播(1ホップ・相互kNN縁のみ)。
    # 引用・近さのグラフで近傍をたどる層(GraphRAG の考え方)。候補が増えるのはここまで
    try:
        from services import graph as _graph

        scores = _graph.expand_scores(db, scores)
        rows.update({
            r.defect_id: r
            for r in db.query(DefectReport).filter(
                DefectReport.defect_id.in_([d for d in scores if d not in rows])
            ).all()
        })
    except Exception:
        pass  # グラフ層は任意機能。失敗しても検索本体は続行

    # フレーズ一致ブースト: クエリの連続12文字窓が本文にそのまま現れる文書を強く優遇。
    # RRF は順位のみで融合するため「ほぼ逐語一致」の文書が僅差で埋もれることがある
    # (帳票の文言をそのまま貼って探すユースケース)。決定論・候補集合内のみで安価。
    qn = _normalize(query)
    if len(qn) >= 12:
        windows = {qn[i : i + 12] for i in range(0, len(qn) - 11, 6)}
        for did in list(scores):
            row = rows.get(did)
            if row is None:
                continue
            text = _normalize(
                " ".join(filter(None, [row.defect_description, row.cause, row.countermeasure, row.good_condition]))
            )
            hits = sum(1 for w in windows if w in text)
            if hits:
                scores[did] *= 1.0 + min(hits, 4) * 0.8  # 1窓=×1.8 〜 4窓以上=×4.2

    mode = "hybrid" if dense_hits else "bm25"
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    out = []
    for did, score in ranked:
        r = rows.get(did)
        if r is None:
            continue
        doc = f"{r.defect_description or ''}\n原因: {r.cause or ''}\n対策: {r.countermeasure or ''}"
        out.append(
            {
                "defect_id": did,
                "part_name": r.part_name,
                "machine_name": r.machine_name,
                "process": r.process,
                "phenomenon": r.phenomenon,
                "snippet": _snippet(doc),
                "score": round(score, 4),
                "search_mode": mode,
            }
        )
    return out
