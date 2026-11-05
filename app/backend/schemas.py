"""Pydantic スキーマ定義。

API のリクエスト/レスポンス形状は docs/03・docs/04 に一致させる。
ReportOut は全カラム + 派生値 `defect_rate` を返す。
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, computed_field


class ReportBase(BaseModel):
    """報告書の共通フィールド(作成・更新で使い回す)。"""

    occurrence_date: date | None = None
    report_date: date | None = None
    customer: str | None = None
    discoverer: str | None = None
    process: str | None = None
    machine_name: str | None = None
    operator_name: str | None = None
    part_number: str | None = None
    part_name: str | None = None
    production_count: int | None = None
    defect_count: int | None = None
    defect_description: str | None = None
    good_condition: str | None = None
    phenomenon: str | None = None
    cause: str | None = None
    factor: str | None = None
    category_4m: str | None = None
    severity: str | None = None
    status: str | None = None
    countermeasure: str | None = None
    material_cost: float | None = None
    processing_cost: float | None = None
    outsourcing_cost: float | None = None
    other_cost: float | None = None
    total_cost: float | None = None
    is_recurrence: bool | None = None
    has_procedure: bool | None = None
    notes: str | None = None
    ai_improvement: str | None = None


class ReportCreate(ReportBase):
    """新規作成。defect_id 未指定ならサーバ側で採番する。

    必須項目(docs/03)は作成時に検証する。
    """

    defect_id: str | None = None
    occurrence_date: date
    customer: str
    process: str
    machine_name: str
    operator_name: str
    part_number: str
    part_name: str
    production_count: int
    defect_count: int
    defect_description: str
    phenomenon: str
    severity: str
    status: str = "open"


class ReportUpdate(ReportBase):
    """部分更新。渡されたフィールドのみ反映する。"""


class ReportOut(ReportBase):
    """詳細レスポンス。全カラム + defect_rate。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    defect_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def defect_rate(self) -> float | None:
        """不適合数 / 加工数(0除算時は None)。"""
        if not self.production_count:
            return None
        return self.defect_count / self.production_count


class ReportList(BaseModel):
    """一覧レスポンス。"""

    total: int
    items: list[ReportOut]


# --- 取り込み(ingest) ---


class IngestResult(BaseModel):
    """帳票取り込み結果(保存はしない・確認画面用)。"""

    extracted: dict
    confidence: str  # high / medium / low
    warnings: list[str] = []
    source_filename: str
    field_checks: dict | None = None   # 判断モデルが画像と照らした項目ごとの結果 {field: {p, ok, box?}}
    verification: dict | None = None   # {model, cost_usd, mismatch} 確信度の決め方の根拠


# --- チャット ---


class ChatMessage(BaseModel):
    role: str  # user / assistant
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []  # 互換用。session_id 指定時は無視し DB 履歴を使う
    session_id: int | None = None


class ChatSource(BaseModel):
    defect_id: str
    part_name: str | None = None
    phenomenon: str | None = None
    snippet: str
    score: float


class ChatResponse(BaseModel):
    """非ストリーミング版チャットの応答(テスト用)。"""

    answer: str
    sources: list[ChatSource] = []
    session_id: int | None = None
    route: dict | None = None        # 判断モデルが決めた質問の種類(DECISIONS_ENABLED=1 のとき)
    citations: dict | None = None    # 判断モデルによる引用の確かめ


# --- チャット履歴(永続化) ---


class ChatSessionOut(BaseModel):
    """会話セッション(一覧・詳細のメタ情報)。"""

    id: int
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ChatMessageOut(BaseModel):
    """会話メッセージ(sources/tools は JSON をパースして返す)。"""

    id: int
    role: str
    content: str
    sources: list | None = None
    tools: list | None = None
    thinking: str | None = None
    created_at: datetime


class ChatSessionDetail(BaseModel):
    """セッション詳細(メタ + メッセージ列)。"""

    session: ChatSessionOut
    messages: list[ChatMessageOut]


# --- マスタ管理 ---


class MasterCreate(BaseModel):
    name: str


class MasterUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class MasterOut(BaseModel):
    """マスタ1件(usage_count = 対応カラムでの使用件数)。"""

    id: int
    category: str
    name: str
    sort_order: int
    is_active: bool
    usage_count: int = 0


class MasterUpdateOut(MasterOut):
    """更新レスポンス(リネーム伝播した報告書件数を付与)。"""

    updated_reports: int = 0


# --- スマート検索(意味検索) ---

class SmartSearchResult(BaseModel):
    """GET /api/reports/search の1件(rag.search の出力)。"""
    defect_id: str
    part_name: str | None = None
    machine_name: str | None = None
    process: str | None = None
    phenomenon: str | None = None
    snippet: str
    score: float
    search_mode: str
    relevance: float | None = None   # 判断モデルが付けた「質問に当てはまる確率」(hybrid+rerank のとき)


class SmartSearchResponse(BaseModel):
    items: list[SmartSearchResult]
    search_mode: str  # hybrid / bm25 / keyword(先頭件の判定)
