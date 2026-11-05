"""【2026-09-27 以降は使わない】この台本は 2026-09-26 までの Word 仕様書を作っていた。
今の docs/DefectReport_AI_仕様書.docx は、仕様書 v5.0(docs/00〜06・13)を pandoc で1冊にしたもの:
  cd docs && pandoc --toc 00_帳票の調査.md 01_要件定義書.md 02_機能仕様書.md 03_データモデル設計書.md \
    04_API設計書.md 05_UI設計書.md 06_AI設計書.md 13_試験・運用仕様書.md -o DefectReport_AI_仕様書.docx
"""
# -*- coding: utf-8 -*-
"""DefectReport AI 仕様書(Word)生成 — 一般的な RAG システム仕様書の
構成(番号付き章立て・項目/内容表・段階導入・受入条件)に倣い、本アプリ仕様へ書き下ろす。

実行: ../.venv/bin/python make_spec_docx.py  → DefectReport_AI_仕様書.docx
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

HERE = Path(__file__).parent
OUT = HERE / "DefectReport_AI_仕様書.docx"
NAVY = RGBColor(0x2F, 0x4A, 0x5E)
TODAY = dt.date(2026, 9, 5)

doc = Document()

# --- 基本スタイル(游ゴシック系、見出しはネイビー) ---
style = doc.styles["Normal"]
style.font.name = "Yu Gothic"
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn("w:eastAsia"), "游ゴシック")
for name, size in (("Title", 24), ("Heading 1", 14), ("Heading 2", 12)):
    st = doc.styles[name]
    st.font.name = "Yu Gothic"
    st.font.size = Pt(size)
    st.font.color.rgb = NAVY
    st.element.get_or_add_rPr()
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "游ゴシック")
for sec in doc.sections:
    sec.top_margin = sec.bottom_margin = Mm(20)
    sec.left_margin = sec.right_margin = Mm(20)


def h1(text: str) -> None:
    doc.add_heading(text, level=1)


def h2(text: str) -> None:
    doc.add_heading(text, level=2)


def p(text: str) -> None:
    doc.add_paragraph(text)


def bullets(items: list[str]) -> None:
    for it in items:
        doc.add_paragraph(it, style="List Bullet")


def kv_table(rows: list[tuple[str, str]], widths=(38, 132)) -> None:
    t = doc.add_table(rows=len(rows) + 1, cols=2)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    hdr[0].text, hdr[1].text = "項目", "内容"
    for c in hdr:
        c.paragraphs[0].runs[0].bold = True
    for i, (k, v) in enumerate(rows, start=1):
        t.rows[i].cells[0].text = k
        t.rows[i].cells[1].text = v
    for row in t.rows:
        row.cells[0].width = Mm(widths[0])
        row.cells[1].width = Mm(widths[1])
    doc.add_paragraph()


def grid_table(header: list[str], rows: list[list[str]]) -> None:
    t = doc.add_table(rows=len(rows) + 1, cols=len(header))
    t.style = "Table Grid"
    for j, htxt in enumerate(header):
        cell = t.rows[0].cells[j]
        cell.text = htxt
        cell.paragraphs[0].runs[0].bold = True
    for i, r in enumerate(rows, start=1):
        for j, v in enumerate(r):
            t.rows[i].cells[j].text = v
    doc.add_paragraph()


def ascii_box(text: str) -> None:
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    cell.text = text
    for para in cell.paragraphs:
        for run in para.runs:
            run.font.name = "MS Gothic"
            run.font.size = Pt(9)
            run.element.rPr.rFonts.set(qn("w:eastAsia"), "MS ゴシック")
    doc.add_paragraph()


def add_image(name: str, width_mm: int = 170) -> None:
    """docs/images の mingrammer/diagrams 生成図を中央寄せで貼る。"""
    img = HERE / "images" / name
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.add_run().add_picture(str(img), width=Mm(width_mm))
    doc.add_paragraph()


# ============================ 表紙 ============================
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run("\n\n\n不適合報告書AI分析システム\nDefectReport AI 仕様書")
run.bold = True
run.font.size = Pt(26)
run.font.color.rgb = NAVY
sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
r2 = sub.add_run(f"\n株式会社霧沢精機 霧沢工場(架空)\n2026年度 AIセミナー 完成イメージアプリ\n\n{TODAY.isoformat()} 版")
r2.font.size = Pt(12)
doc.add_page_break()

# ============================ 1. 文書情報 ============================
h1("1. 文書情報")
kv_table([
    ("文書名", "不適合報告書AI分析システム(DefectReport AI)仕様書"),
    ("版", f"1.0({TODAY.isoformat()})"),
    ("作成", "2026年度 AIセミナー(山梨大学 LEOW Chee Siang)"),
    ("位置づけ", "セミナー第3〜7回で受講者が構築する完成イメージアプリの仕様。実装済みシステムの記述であり、調達仕様ではない"),
    ("対象読者", "セミナー受講者、講師、製造業DX担当者"),
    ("関連文書", "docs/01〜10(要件定義・機能仕様・データモデル・API・UI・AI設計・発展・技術・分析・提案)"),
    ("注意", "登場する会社・工場・人名・データはすべて架空。機械名のみ実在市販機種名を使用"),
])

h1("2. システムの位置づけと背景")
p("製造業の品質保証部門では、不適合報告書(不良報告書)が紙・Excel・PDFで散在し、"
  "過去の類似不良の検索、傾向分析、是正処置(CAPA)の追跡に多大な工数を要している。"
  "本システムは、蓄積された不適合報告書をAIで構造化・検索・分析し、"
  "根拠付きの回答と画面操作を行う品質保証アシスタントの完成イメージを示す。")
bullets([
    "セミナー第3回(土台)〜第7回(仕上げ)のステップ実装の到達点",
    "文書検索 RAG で効果が確かめられている設計"
    "(ハイブリッド検索・ファセット層・同義語辞書・GraphRAG・品質評価)を製造業データへ応用",
])

h1("3. システムの目的")
bullets([
    "不適合報告書(Excel/PDF/画像)のAI構造化取込と一元管理",
    "自然言語での検索・質問応答(根拠となる報告書IDを必ず引用)",
    "4M分析(Man/Machine/Material/Method)と改善提案の自動生成",
    "KPIダッシュボード・予兆アラートによる経営層向け可視化",
    "類似事例サジェスト・CAPA・8Dレポートによる是正処置の実務支援",
    "AIアシスタントによる画面の直接操作(WebMCP)で、対話とUIを一体化",
])

h1("4. 基本方針")
h2("4.1 根拠優先(毎ターン独立の原則)")
p("AIの回答は必ずそのターンでツールにより取得した実データに基づく。"
  "会話履歴や過去ターンのツール結果から報告書の内容を再構成することは捏造として禁止する。")
h2("4.2 出典の明示")
p("報告書を参照した回答には [KZ25-XXXX] 形式のIDを必ず引用し、画面上で当該報告書へのリンクとして機能させる。")
h2("4.3 画面操作の実行保証")
p("「画面を操作した・開いた・並び替えた」と回答する前に、必ず対応する ui_* ツールを実際に呼ぶ。"
  "ツールを呼ばない操作完了の主張は虚偽主張として評価で検出する(false_claim 指標)。")
h2("4.4 書き込みの安全規則")
p("報告書・CAPAの登録/更新はユーザーの明示的な依頼があるときのみ実行する。削除はAIから実行できない。")
h2("4.5 人間による最終判断")
p("AIの分析・ドラフト(4M分析、CAPAドラフト、8Dレポート、外観所見)は提案であり、採用・登録は人間が確定する。")

h1("5. 対象範囲")
h2("5.1 対象とする情報")
bullets([
    "不適合報告書(発生日・客先・工程・機械・部品・数量・不適合内容・原因・対策・費用等の23項目)",
    "帳票ファイル(様式 QF-07-03: Excel/PDF/写真画像)",
    "マスタ(機械・工程・客先・作業者・現象)",
    "是正処置(CAPA)・週次ダイジェスト・チャット履歴・回答フィードバック",
])
h2("5.2 対象外")
bullets([
    "認証・権限管理(全機能をログインなしで利用。実運用ではSSO等を要検討)",
    "多言語対応、承認ワークフロー、Neo4j等のグラフDB(docs/07 発展トピック)",
])

h1("6. 利用者区分と想定利用例")
grid_table(["区分", "主な利用"], [
    ["品質保証担当", "報告書の起票・検索・類似事例参照・CAPA管理・8D作成"],
    ["製造現場", "音声入力での起票補助、写真添付、対策の確認"],
    ["経営層・管理職", "KPIダッシュボード・週次ダイジェスト・予兆アラート"],
    ["セミナー受講者", "各機能の実装ステップ(第3〜7回)の教材として"],
])
h2("6.1 想定利用例")
bullets([
    "「GENOS M560-Vで最近多い不具合は?」→ ツールで実データを集計し、ID引用付きで回答",
    "「治具の固定が甘くてワークがずれたような事例」→ スマート検索(意味検索)で類似報告を提示",
    "「翠峰重工業のMethod起因を損失額順で一覧にして」→ ui_navigate で一覧画面をその条件で表示",
    "「KZ25-0087の是正処置ドラフトを考えて」→ 類似事例の対策からAIがドラフト(登録は明示依頼時のみ)",
])

h1("7. システム構成")
h2("7.1 全体構成")
p("全体アーキテクチャ(mingrammer/diagrams で生成。再生成: docs/diagrams/generate_diagrams.py):")
add_image("architecture.png")
h2("7.2 サービス一覧(Docker Compose)")
grid_table(["サービス", "役割", "ポート"], [
    ["db", "PostgreSQL 16(報告書・マスタ・チャット履歴・CAPA・フィードバックの正本)", "内部5432"],
    ["backend", "FastAPI(REST + MCP + SSE)。SQLite フォールバックあり", "8000"],
    ["opencode", "OpenCode サーバー(チャット・抽出・4MのLLM実行系)", "内部4096"],
    ["frontend", "React ビルド済み静的配信 + API プロキシ(nginx)", "5373(既定5173)"],
    ["langfuse / langfuse-db", "LLM可観測性(トレース・スコア)。ヘッドレス初期化済み", "3390"],
])

h1("8. データ仕様")
h2("8.1 完全架空データ")
p("実データの流用を避けるため、世界観を data/fictional_world.json に固定した完全架空データを使用する。"
  "会社=株式会社霧沢精機、客先10社(翠峰重工業ほか)、担当者30名、部品カタログはP/V/C/A系列。"
  "機械名のみ実在市販機種(QUICK TURN 250MSY、GENOS M560-V、DMU 65 monoBLOCK 等12機種)を使用する。")
kv_table([
    ("報告書ID", "KZ25-XXXX(KZ=霧沢、25=2025年度、4桁連番)。全117件"),
    ("部品番号", "KRS-{系列}{2桁}-{4桁}-{A-E}"),
    ("期間", "2025-04-01 〜 2026-03-31(月別の繁閑あり: 7月・11月に山)"),
    ("数量分布", "加工数1〜500のロングテール、不適合数は加工数の2〜40%、損失額は数千円〜百万円超の対数正規風"),
    ("生成", "data/generate_mock_data.py(seed=774123)。全記述文はテンプレート+可変要素で同文重複なし"),
    ("帳票", "様式 QF-07-03(Excel全117件 / PDF先頭10件)。取込機能のラベル走査と対応"),
])
h2("8.2 主要テーブル")
grid_table(["テーブル", "内容"], [
    ["defect_reports", "不適合報告書(23項目+AI改善提案)"],
    ["masters", "機械・工程・客先・作業者・現象マスタ"],
    ["chat_sessions / chat_messages", "チャット履歴(sources・tools・thinking含む)"],
    ["capa_actions", "是正処置(CA-XXXX、open→in_progress→effect_check→closed)"],
    ["weekly_digests / eight_d_reports", "週次ダイジェスト / 8Dレポート"],
    ["chat_feedback", "回答への👍/👎+コメント(Langfuse trace_id 紐づけ)"],
])

h1("9. 帳票取込機能")
bullets([
    "Excel(QF-07-03): ラベルセル走査で決定論抽出(「数量」=不良/加工併記のパース、節見出しからの現象/要因/4M抽出)",
    "PDF/画像: OpenCode(vision)による構造化抽出。ANTHROPIC_API_KEY があれば Anthropic 直も可",
    "抽出結果は確認画面で人間が修正してから登録(confidence と warnings を表示)",
])

h1("10. 検索・RAG機能")
h2("10.1 ハイブリッド検索")
p("形態素BM25(SudachiPy、未導入時は文字バイグラム)と密ベクトル(multilingual-e5-small)を"
  "RRF(k=60)で融合する。密ベクトルだけより順位が良くなりやすい、という一般的な知見に基づく構成。")
h2("10.2 補正層(すべて決定論・LLM不使用)")
grid_table(["層", "内容"], [
    ["同義語展開", "手書き辞書(23群)+コーパス駆動自動生成辞書(scripts/build_synonyms.py: LLM候補→実在検証→採用)"],
    ["ファセット層", "機械/工程/重大度/4Mをクエリと突き合わせ、不一致×0.55・一致×1.15"],
    ["フレーズ一致", "クエリの連続12文字窓が本文に逐語出現する文書を×1.8〜×4.2(帳票文言の貼り付け検索対応)"],
    ["グラフ展開", "相互kNNグラフ(埋め込み再利用)の強い縁へ α=0.25 で1ホップ減衰伝播(GraphRAG層)"],
])
p("検索パイプライン全体像:")
add_image("search_pipeline.png", width_mm=165)
h2("10.3 スマート検索(画面)")
p("一覧・検索画面のモード切替で自然文検索を提供(GET /api/reports/search)。"
  "結果には類似度スコアと抜粋を表示し、機械・工程の後段絞り込みが可能。")

h1("11. 回答生成仕様")
kv_table([
    ("エンジン", "OpenCode + OpenRouter(既定 anthropic/claude-sonnet-4.5、出力上限8000トークン)"),
    ("文脈注入", "ハイブリッド検索上位を「参考」として注入+MCPツールで自律取得"),
    ("引用", "[KZ25-XXXX] 形式必須。画面でリンク化(MarkdownMessage)"),
    ("回答不能時", "『見つかりません/存在しません』と明言し、存在しないIDを提示しない(幻覚プローブで検証)"),
    ("Markdown", "太字・箇条書き・表・リンクをレンダリング"),
    ("空応答", "モデル未応答は明示エラー化(利用者・評価系がリトライ可能)"),
])

p("チャット1リクエストのデータフロー(番号付き):")
add_image("chat_flow.png")

h1("12. 画面仕様")
h2("12.1 レイアウト")
p("3カラム構成(メニュー | AIアシスタント常駐パネル | メイン画面)。"
  "チャット幅はドラッグで300〜640pxに可変。lg(1200px)未満ではハンバーガー+チャット左オーバーレイの"
  "レスポンシブ構成に自動切替。ライト/ダークテーマ対応。")
h2("12.2 画面一覧")
grid_table(["画面", "パス", "主な機能"], [
    ["サマリー", "/dashboard", "KPI・パレート図・p管理図・期間フィルタ"],
    ["予測アラート", "/alerts", "ルールベース予兆(不良率上昇・急増・対策後再発・連続上昇)"],
    ["週次レポート", "/digests", "週次ダイジェスト一覧・生成(KPI前週比+AI所見)"],
    ["一覧・検索", "/reports", "9フィルタ+期間+並び順+スマート検索(URLクエリが正本)"],
    ["報告書詳細", "/reports/{id}", "全項目・4M分析・写真・類似事例・CAPA・8D"],
    ["新規作成", "/reports/new", "手入力+帳票取込+音声入力(対応ブラウザ)"],
    ["是正処置", "/capa", "CAPA一覧・状態管理(closedは効果確認メモ必須)"],
    ["分析4種", "/analysis/*", "機械別・担当者別・顧客別・時系列"],
    ["関連マップ", "/analysis/graph", "報告書の近さの地図(相互kNN・力学レイアウト)"],
    ["チャット", "/chat", "全画面チャット(履歴・復元・削除)"],
    ["マスタ管理", "/settings/masters", "5カテゴリのマスタCRUD"],
])
h2("12.3 AIによる画面操作(WebMCP)")
p("チャットAIは ui_* ツール → SSE(/api/ui/events)→ UiControlBridge の経路で"
  "上記すべての画面遷移・フィルタ・ソート・スマート検索・テーマ切替・編集モード起動を実行できる。"
  "人間のUI操作とAIの操作はURLクエリパラメータを共通制御点とし、同じ状態を共有する。")

h1("13. MCPツール仕様(22本)")
grid_table(["種別", "ツール", "用途"], [
    ["読取(8)", "list/search/get_defect_report(s), get_statistics, get_control_chart, get_active_alerts, list_masters, get_similar_reports", "一覧・類似検索・詳細・KPI・p管理図・アラート・マスタ・類似事例"],
    ["書込(2)", "create/update_defect_report", "明示依頼時のみ。update は8項目限定"],
    ["CAPA(5)", "list/draft/create/update_capa_actions, generate_8d_report", "是正処置の参照・AIドラフト・起票・更新・8D生成"],
    ["集計(1)", "generate_weekly_digest", "週次ダイジェスト生成"],
    ["画面(6)", "ui_navigate, ui_open_report, ui_new_report, ui_edit_report, ui_run_4m_analysis, ui_set_theme", "全画面の遷移・操作(4.3の実行保証に従う)"],
])

h1("14. フィードバック・可観測性")
h2("14.1 回答フィードバック")
p("各AI回答に👍/👎ボタンを表示。👎は任意コメント付き(例: 引用と内容が不一致)。"
  "POST /api/chat/feedback に保存し、週次ダイジェストのKPI表へ集計する。")
h2("14.2 Langfuse トレーシング")
p("チャット1件=1トレース(rag_sources スパン+opencode 生成)として Langfuse に記録し、"
  "👍/👎は user-feedback スコアとしてトレースに紐づく(done イベントの trace_id 経由)。"
  "LANGFUSE_* 未設定時は自動で無効化され、本体動作に影響しない。"
  "UI: http://localhost:3390(admin@example.com / langfuse-admin、キーはヘッドレス初期化済み)。")

h1("15. API要件(主要エンドポイント)")
grid_table(["メソッド/パス", "内容"], [
    ["GET/POST /api/reports, GET/PATCH/DELETE /api/reports/{id}", "報告書CRUD(9条件+期間+並び順)"],
    ["GET /api/reports/search", "スマート検索(ハイブリッド)"],
    ["GET /api/reports/{id}/similar", "類似事例サジェスト"],
    ["POST /api/ingest/upload", "帳票取込(Excel/PDF/画像)"],
    ["POST /api/chat/stream", "SSEチャット(session/sources/tool/thinking/token/done/error)"],
    ["POST/GET /api/chat/feedback", "回答フィードバック"],
    ["GET /api/dashboard/statistics ほか", "KPI・p管理図・アラート・内訳・トレンド"],
    ["GET/POST /api/digests(+/generate)", "週次ダイジェスト"],
    ["GET/POST/PATCH /api/capa(+/draft, /eight-d)", "CAPA・8D"],
    ["GET/POST/DELETE /api/reports/{id}/photos(+/analyze)", "写真+AI外観所見"],
    ["GET /api/graph", "関連マップ(節・縁)"],
    ["POST /api/ui/navigate|open_report/{id}|command, GET /api/ui/events", "画面操作(REST+SSE)"],
])

h1("16. 品質評価仕様")
h2("16.1 評価データ")
p("架空データをGround Truthとして決定論生成する38ケース(eval/make_dataset.py, seed=0)。"
  "fact 10 / aggregate 8 / semantic 3 / fabrication 5 / ui 8 / multiturn 4。")
h2("16.2 評価指標")
grid_table(["指標", "内容"], [
    ["correct", "期待値(機械名・件数・ID等)が回答に含まれる"],
    ["tool_ok", "カテゴリごとの必須ツール(required_tools)を実際に呼んだ"],
    ["false_claim", "画面操作を主張したのに ui_* 未呼び出し(虚偽主張)の検出"],
    ["citation_valid", "引用IDが全件実在(幻覚ID検出。否定文・例示中の言及は除外)"],
    ["fabrication_ok", "存在しない対象に、DBを確認したうえで『存在しない』と回答"],
    ["faithfulness / relevancy", "RAGAS準拠のLLM判定(gpt-4o-mini judge)0〜1"],
])
h2("16.3 実測と受入基準")
p("2026-09-05 実測(26ケース時点): 正答26/26、幻覚ID引用0件、faithfulness 0.93〜1.00。"
  "受入基準案: 正答率90%以上、幻覚ID引用0件、ui カテゴリの tool_ok 100%、虚偽主張0件。")
h2("16.4 マルチターン評価")
p("実際に観測された失敗(会話が続いた状態で『開いて』にツールを呼ばず内容を捏造)を再現する"
  "multiturn カテゴリを常設し、毎ターン独立の原則(4.1)の遵守を回帰的に検証する。")

h1("17. テスト仕様")
bullets([
    "単体・結合: pytest 50件(API・ハイブリッド検索・グラフ・フィードバック・取込)",
    "E2E(Playwright): ui_navigate 総当たり18ケース、レスポンシブ4ビューポート、Markdown描画、チャットWebMCP実ブラウザ",
    "デモスクリプト: e2e/demo_new_features.py(ヘッドあり・スクリーンショット出力)",
])

h1("18. セキュリティ・個人情報")
bullets([
    "全データが架空のため個人情報・機密情報を含まない(実運用では入力情報の保護・PII検知を要検討)",
    "AIの書き込みは明示依頼時のみ・削除不可(4.4)。画面操作はデータ変更なし",
    "プロンプトインジェクション対策: ツールは構造化引数のみ、システム指針(AGENTS.md)で毎ターン独立を強制",
    "外部通信は OpenRouter(LLM)のみ。Langfuse・DB・検索はすべてローカル",
])

h1("19. 運用")
kv_table([
    ("起動", "cd app && FRONTEND_PORT=5373 docker compose up -d --build"),
    ("必須キー", "OPENROUTER_API_KEY(.env)。残高不足時は402で全AI機能が縮退するため残高監視が必要"),
    ("MCP変更時", "docker compose restart opencode(AGENTS.md変更時はイメージ再ビルド)"),
    ("データ再生成", "data/generate_mock_data.py 実行後、down -v で再シード+eval/make_dataset.py 再実行"),
    ("同義語辞書更新", "docker compose exec backend python scripts/build_synonyms.py --apply"),
    ("週次ダイジェスト", "画面の「今すぐ生成」または cron で POST /api/digests/generate"),
])

h1("20. 導入段階(セミナー対応)")
grid_table(["段階", "内容"], [
    ["第3回(土台)", "FastAPI+React の CRUD・ダッシュボード(steps/step01)"],
    ["第4回(Claude API)", "LLM連携・4M分析(steps/step02)"],
    ["第5回(RAG・取込)", "ベクトル検索・帳票取込・引用チャット(steps/step03)"],
    ["第6回(KPI分析)", "統計・管理図・アラート(steps/step04)"],
    ["第7回(仕上げ)", "MCP・WebMCP・CAPA・評価・可観測性(steps/step05=本仕様の完成形)"],
])

h1("21. 主要リスクと対策")
grid_table(["リスク", "対策"], [
    ["LLMの幻覚(存在しないID・数値)", "毎ターン独立の原則+幻覚プローブ評価+引用ID実在チェック"],
    ["ツール未実行のまま操作完了を主張", "instructions/AGENTS.md の実行保証+false_claim 検出+multiturn 評価"],
    ["APIクレジット枯渇による無応答", "空応答の明示エラー化+出力上限8000+残高監視(19章)"],
    ["検索の取りこぼし", "ハイブリッド+同義語+フレーズ一致+グラフ展開の多層構成"],
    ["実データの混入", "fictional_world.json による世界観固定+禁止トークン検査"],
])

h1("22. 免責表示案")
p("本システムの回答はAIによる参考情報であり、品質判定・出荷可否・顧客対応の最終判断は"
  "品質保証責任者が行ってください。回答には必ず根拠となる報告書IDが引用されます。"
  "引用がない、または内容に疑義がある場合は👎ボタンからご報告ください。")

doc.save(OUT)
print(f"saved: {OUT} ({OUT.stat().st_size:,} bytes)")
