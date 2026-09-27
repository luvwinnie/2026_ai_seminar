"""不適合報告書テーブル定義(docs/03 データモデル設計書に準拠)。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from database import Base


class DefectReport(Base):
    """不適合報告書の正本。API の JSON フィールド名もこの属性名に一致させる。"""

    __tablename__ = "defect_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    defect_id = Column(String, unique=True, nullable=False, index=True)  # KZ25-0001 形式

    occurrence_date = Column(Date, nullable=False)  # 発生日
    report_date = Column(Date)  # 報告日

    customer = Column(String, nullable=False)  # 客先
    discoverer = Column(String)  # 発見者名
    process = Column(String, nullable=False)  # 発生工程
    machine_name = Column(String, nullable=False)  # 使用機械
    operator_name = Column(String, nullable=False)  # 作業者名

    part_number = Column(String, nullable=False)  # 部品番号
    part_name = Column(String, nullable=False)  # 部品名称
    production_count = Column(Integer, nullable=False)  # 加工数
    defect_count = Column(Integer, nullable=False)  # 不適合数

    defect_description = Column(Text, nullable=False)  # 不具合内容
    good_condition = Column(Text)  # 良品状態
    phenomenon = Column(String, nullable=False)  # 現象分類
    cause = Column(Text)  # 原因
    factor = Column(String)  # 要因
    category_4m = Column(String)  # 4M分類(Man/Machine/Material/Method)

    severity = Column(String, nullable=False)  # critical/high/medium/low
    status = Column(String, nullable=False, default="open")  # open/in_progress/completed
    countermeasure = Column(Text)  # 対策

    material_cost = Column(Numeric)  # 材料費
    processing_cost = Column(Numeric)  # 社内加工費
    outsourcing_cost = Column(Numeric)  # 外注加工費
    other_cost = Column(Numeric)  # その他費用
    total_cost = Column(Numeric)  # 合計損失

    is_recurrence = Column(Boolean, default=False)  # 再発フラグ
    has_procedure = Column(Boolean, default=True)  # 手順書有無
    notes = Column(Text)  # 備考
    ai_improvement = Column(Text)  # AI生成の改善提案

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    @property
    def defect_rate(self) -> float | None:
        """派生値: 不適合数 / 加工数(0除算時は None)。"""
        if not self.production_count:
            return None
        return self.defect_count / self.production_count


class MasterItem(Base):
    """ドロップダウン選択肢のマスタ(客先・工程・機械・作業者・現象・要因の6カテゴリ)。"""

    __tablename__ = "masters"
    __table_args__ = (UniqueConstraint("category", "name", name="uq_masters_category_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, nullable=False, index=True)  # customer/process/machine/operator/phenomenon/factor
    name = Column(String, nullable=False)  # 選択肢名
    sort_order = Column(Integer, nullable=False, default=0)  # 表示順(小さいほど上)
    is_active = Column(Boolean, nullable=False, default=True)  # 無効化で候補から除外
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class ChatSession(Base):
    """チャットの会話セッション(過去履歴の単位)。"""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String)  # 先頭メッセージ由来のタイトル
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class ChatMessage(Base):
    """チャット1メッセージ。sources/tools は JSON 文字列で保持する。"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String, nullable=False)  # user / assistant
    content = Column(Text, nullable=False)  # 本文
    sources_json = Column(Text)  # 参照報告書(JSON配列文字列)
    tools_json = Column(Text)  # ツール実行の最終状態(JSON配列文字列)
    thinking = Column(Text)  # 推論テキスト(蓄積)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class WeeklyDigest(Base):
    """週次品質ダイジェスト(docs/10 A-2)。AIが定期生成するMarkdownレポート。"""

    __tablename__ = "weekly_digests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    period_start = Column(Date, nullable=False)  # 集計開始日
    period_end = Column(Date, nullable=False)  # 集計終了日(この日を含む)
    content_md = Column(Text, nullable=False)  # レポート本文(Markdown)
    ai_backend = Column(String)  # 生成に使ったAI("opencode"/"none"=決定論のみ)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class CapaAction(Base):
    """是正・予防処置(CAPA)のアクション(docs/10 A-3)。不適合報告書に紐づく。"""

    __tablename__ = "capa_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    capa_id = Column(String, unique=True, nullable=False, index=True)  # CA-0001 形式
    defect_id = Column(String, nullable=False, index=True)  # 対象報告書(KZ25-XXXX)
    action_type = Column(String, nullable=False, default="corrective")  # corrective / preventive
    title = Column(String, nullable=False)  # 処置の要約
    description = Column(Text)  # 処置の詳細
    owner = Column(String)  # 担当者
    due_date = Column(Date)  # 期限
    status = Column(String, nullable=False, default="open")  # open/in_progress/effect_check/closed
    effect_note = Column(Text)  # 効果確認メモ(closedへの遷移時に記入)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class EightDReport(Base):
    """8Dレポート(docs/10 A-3)。報告書+類似事例+CAPAからAIが生成するD1〜D8文書。"""

    __tablename__ = "eight_d_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    defect_id = Column(String, nullable=False, index=True)
    content_md = Column(Text, nullable=False)
    ai_backend = Column(String)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class ChatFeedback(Base):
    """チャット回答への利用者フィードバック(試用段階の一般的な改善ループ)。

    試用中の指摘(「根拠の紐づけが違う」など)はメール等に散らばりやすい。アプリ内に 👍/👎+コメントの
    導線を置き、週次ダイジェストにも集計して品質改善ループを回す。
    """

    __tablename__ = "chat_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, index=True)
    message_index = Column(Integer)  # セッション内の何番目のメッセージへの評価か
    rating = Column(Integer, nullable=False)  # +1 / -1
    trace_id = Column(String)  # Langfuse トレースID(スコア紐づけ用・任意)
    comment = Column(Text)
    answer_excerpt = Column(Text)  # 評価対象回答の先頭(照合用)
    question_excerpt = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class TriageRun(Base):
    """報告書トリアージ(判断モデル Jev + LangGraph)の1回ぶんの結果。

    途中の状態は LangGraph のチェックポイント(data/triage_checkpoints.db)にあり、
    ここには画面に出す最新の結果と状態(completed / waiting_approval / approved / rejected)を置く。
    """

    __tablename__ = "triage_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, unique=True, nullable=False, index=True)  # tr-xxxxxxxxxxxx(グラフの thread_id)
    defect_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="completed")
    result_json = Column(Text)  # 判断・通ったノード・CAPA 案など(JSON)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
