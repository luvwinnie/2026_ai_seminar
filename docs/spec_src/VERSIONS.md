# 仕様書の版と、版ごとに足すもの（正本の書き方の決まり）

例アプリ DefectReport AI の仕様書を、講座の回ごとに少しずつ育つ形で書く。
正本は1つ（このフォルダの `00_〜07_*.md`）で、各部分に「どの版から入るか」の印を付ける。
`render_versions.py` が版ごとの仕様書を書き出す。v5.0 が完成形（＝例アプリ）の仕様書。

## 1. 版の並び

| 版 | 講座 | その版の意味 |
|---|---|---|
| v0.1 | 第1回 | 目的メモ（`作りたいアプリ.md`。このフォルダの正本の外。困りごと・使う人・データ・最初にできること） |
| v1.0 | 第2回 前半 | Excel（110件）を調べて書いた最初の仕様書。作る前 |
| v1.1 | 第2回 終わり | 土台を作って確かめ、見つかった穴を戻した版 |
| v2.0 | 第3回 前半 | AI アシスタント（OpenCode＋MCP）を足す仕様 |
| v2.1 | 第3回 終わり | 確かめて見つかったずれを戻した版 |
| v3.0 | 第4回 前半 | 帳票の取込・ハイブリッド検索・引用 |
| v3.1 | 第4回 終わり | 確かめて戻した版 |
| v4.0 | 第5回 前半 | KPI・4M 分析・予兆・評価 |
| v4.1 | 第5回 終わり | 確かめて戻した版 |
| v5.0 | 第6回 | 登録・編集・削除の完成、試験、Docker、運用、完成形の追加機能。例アプリと同じ |

x.0 は「その回で足すことを先に書いた版」、x.1 は「作って確かめ、見つかった穴を戻した版」。
x.1 で足すのは、下の表の「確かめて戻すこと」だけにする（x.1 で新しい機能は足さない）。

## 2. 版ごとに足すもの（台帳）

要件の番号は `01_要件定義書.md` のもの。**この表が正本**。迷ったらここに合わせる。

### v1.0（第2回・土台）
- 要件：FR-SYS-01（/health：状態・件数）、FR-SYS-02（空の DB に模擬データを自動で入れる）、FR-CR-01（一覧：キーワード・状態・重大度・機械・工程・4M・期間で絞り込み、並べ替え、ページ送り。客先・作業者・現象の絞り込みは v2.0 で足す＝MCP の list_defect_reports と同じ条件）、FR-CR-03（詳細。不良率 defect_rate を含む）
- 非機能：NFR-01（手元の PC で動く）、NFR-05（模擬データ110件）、NFR-06（生成は乱数固定で再現できる）、NFR-08（読みやすい作り）、NFR-09（SQLite とローカルのファイルだけで動く）、NFR-10（日本語）
- データ：defect_reports 表（4M 分析の結果の列 ai_improvement は v4.0）。用語表と関係図（報告書・機械・工程・客先・現象・要因と、その関係。業務 Ontology の入口）
- API：GET /health、GET /api/reports、GET /api/reports/{defect_id}
- 画面：全体の枠（メニュー）、/reports 一覧（絞り込み）、/reports/:defectId 詳細
- 00_帳票の調査：様式（改訂B・改訂C）、項目とセル、表記の揺れ、欠損、件数
- 受け入れ条件：件数110、a61nx は3件、2025年9月は7件、a61nx かつ2025年9月は KZ25-0043、a61nx かつ2025年10月は0件（0件の表示）、KZ25-0043 の詳細の値

### v1.1（第2回・確かめて戻すこと）
- 期間は date 型で比べ、両端を含む。不正な日付や date_from > date_to は 422 と理由を返す
- 0件と読み込み失敗を別の表示にする（失敗したら表と件数を消し、原因と「再試行」を出す）
- 絞り込みの選択肢はマスタから作る：masters 表（customer・process・machine・operator・phenomenon・factor の6種）を取込のときにデータの値から作り、GET /api/masters で返す（FR-MA-01）。用語表を正本にする
- 受け入れ条件の期待値は元データから数えて書く（計画の数字は検算する）

### v2.0（第3回・AI アシスタント）
- 要件：FR-CH-01（報告書を根拠に回答）、FR-CH-02（SSE で逐次表示。session・thinking・tool・token・done・error）、FR-CH-06（履歴はサーバーが DB から直近20件）、FR-CH-08（書き込みは利用者がはっきり頼んだときだけ）、FR-CH-09（会話をセッションで保存・復元・削除）
- 非機能：NFR-02（必須のキーは OPENROUTER_API_KEY の1本）。LLM は OpenCode 経由で OpenRouter（既定）。ローカル LLM（Ollama）への切替は任意（発展。接続先は環境変数）
- AI：OpenCode serve（HTTP API）、MCP サーバー（FastAPI に同居、/mcp/、名前 defect-reports）、AGENTS.md（ガードレール：そのターンで道具から取った値だけで答える／存在しない番号を作らない／していない操作を「しました」と言わない／空の応答やエラーを成功にしない）、構造化出力（JSON Schema）の考え方
- MCP の道具（15本）：読み取り list_defect_reports・search_defect_reports（この版はキーワード検索）・get_defect_report・get_statistics・list_masters、書き込み create_defect_report・update_defect_report、画面の操作 ui_navigate・ui_open_report・ui_set_theme、Ontology get_ontology_definition・resolve_ontology_entity・get_ontology_object・traverse_ontology_relation・query_quality_ontology
- 画面の操作（WebMCP）：GET /api/ui/events（SSE）、UiControlBridge。状態の正本は URL クエリ（人の操作と AI の操作が同じ URL を見る）。AI アシスタントは全ページの常駐パネル。ライト／ダークの切替
- データ：chat_sessions・chat_messages。業務 Ontology（app/backend/ontology/quality.json）
- 観測：Langfuse に1問1トレース（done に trace_id）。Langfuse が無くても動く
- 画面：/chat（逐次表示・道具の表示・参照した報告書へのリンク・会話の一覧）、常駐の AI パネル
- 受け入れ条件：「KZ25-0043 の内容を教えて」→ get_defect_report、回答に a61nx／「KZ25-9999」→ 無いと答える／「表面キズは何件？」→ 38件（集計の道具で数える）／再読込しても会話が残る

### v2.1（第3回・確かめて戻すこと）
- 画面を操作したと答える前に、必ず ui_* を呼ぶ（前のターンで操作済みでも毎回。毎ターン独立）
- 空の応答・残高切れ（402）・finish_reason=length は成功にしない。error イベントで理由を出す
- 数量の決まり：0 ≦ 不適合数 ≦ 加工数（構造化出力の検証に使う。登録 API で拒否するのは v5.0）
- Langfuse のトレースに入力（質問）と使ったトークンを必ず残す（input が空・usage が0 だった）

### v3.0（第4回・取込・検索・引用）
- 要件：FR-IN-01〜07（xlsx・pdf・画像を取込、保存せずに確認画面へ、確信度と警告、人が直して登録、AI が無いときの縮退）、FR-CH-03（回答の前に sources）、FR-CH-04（本文で [KZ25-XXXX] を引用）、FR-CH-07（埋め込みが無ければ BM25／キーワードに縮退し、search_mode を明示）
- 検索：BM25（SudachiPy。無ければ文字の bigram）＋ Dense（multilingual-e5-small、passage:/query: の接頭辞、Chroma）を RRF（k=60）で合わせる。同義語辞書 synonyms.json、ファセット補正、候補数を固定。DB が正本、Chroma は写し（登録・更新・削除で索引も直す）
- API：POST /api/ingest/upload、POST /api/ingest/confirm、GET /api/reports/search（スマート検索）、GET /api/reports/{defect_id}/similar（似ている報告書）
- MCP：get_similar_reports、ui_new_report を足す（17本）。search_defect_reports はハイブリッド検索になる
- AI：帳票の構造化抽出（JSON Schema、vision）。Anthropic への直接接続は抽出の代わりの経路（任意）
- データ：Chroma のコレクション defect_reports
- 画面：/reports/new（取込と確認）、一覧の「スマート検索」、詳細の「似ている報告書」
- 受け入れ条件：固定5問（通常・言い換え・属性違い・2資料が必要・根拠なし）と正解の番号、改訂B と改訂C を1件ずつ原本と照合

### v3.1（第4回・確かめて戻すこと）
- 件数・率の質問は、検索の上位の件数で数えず、集計の道具で数える（FR-CH-05）
- 取込の確信度は AI の自己申告ではなく、サーバーの決まりで決める
- PDF・画像は OpenCode にファイル（data URL）として渡す（本文に貼らない）
- DB と索引（Chroma）の件数と ID を突き合わせる方法と、データを入れ替えたら索引を作り直すことを書く

### v4.0（第5回・KPI・分析・評価）
- 要件：FR-DB-01〜06（KPI・月次・パレート・層別・4M 別と重大度別・p 管理図。期間指定）、FR-AN-01〜03（4M 分析。構造化出力、人が採否を決めてから保存）、FR-AL-01〜02（ルールの予兆アラート）
- KPI の定義：分子・分母・期間・単位（件／個／円）。不良率＝Σ不適合数÷Σ加工数（行ごとの率の平均ではない）。データに列が無い指標（OEE・MTBF）は計算できないと書く
- API：GET /api/dashboard/statistics、GET /api/dashboard/control-chart、POST /api/analysis/4m/{defect_id}、GET /api/analysis/alerts ほか分析
- MCP：get_control_chart、get_active_alerts、ui_run_4m_analysis を足す（20本）
- データ：defect_reports.ai_improvement
- 画面：/dashboard（サマリー）、/analysis/machines・operators・customers・trends、/alerts、詳細の「4M 分析」
- 評価：固定の評価セット（事実・集計・検索・捏造・画面操作・複数ターン）、採点規則（答え・道具・引用を分ける）、失敗の分類。直す前と後を比べる
- 受け入れ条件：全期間の件数・不適合数・不良率・損失を pandas の値と一致させる（110件・1,829個・17.49%・36,445,731円）

### v4.1（第5回・確かめて戻すこと）
- 分母が0の率は null（0% と書かない）
- 「直近」の基準日はデータの最新の発生日（今日ではない。模擬データは 2026-03-15 が最後）
- KPI カードのラベルと定義を合わせる（「未対応」は open だけ。対応中 in_progress は別に数える）
- 採点器の穴を直す（日付の和表記、否定文の中の番号、「表示しました」の「し」）

### v5.0（第6回・完成形）
- 予兆のルール4〜6（急増・対策後の再発・3か月連続の上昇）は FR-AL-03 として v5.0
- 要件：FR-CR-02（新規作成。defect_id が無ければ KZ25-<連番>）、FR-CR-04（部分更新。索引も直す）、FR-CR-05（削除。索引からも消す）、FR-CR-06（total_cost はサーバーで合算）、数量の検査（0 ≦ 不適合数 ≦ 加工数。違反は 422 と日本語の理由、保存しない。**例アプリには未実装**＝第6回の演習で入れる）
- 非機能：NFR-03（Docker Compose で6サービス：db＝PostgreSQL 16・backend・opencode・frontend＝nginx・langfuse-db・langfuse。healthcheck、ポートは環境変数）、NFR-04（応答時間の目安）、NFR-07（キーや埋め込みが無くても縮退して動く）、NFR-09 は Docker では PostgreSQL
- MCP：ui_edit_report を足す（本筋21本）
- 画面：詳細の画面で編集する（編集用の別の URL は持たない。ui_edit_report はこの編集の状態を開く）、理由を押した位置に出す
- 試験：pytest（単体・結合）、Playwright（E2E）、結果は件数・日付・コマンドを組で書く。/code-review・/security-review、Hooks
- 運用：起動・停止・復旧（down と down -v の違い）、README だけで別の人が起動できる、Trace に残す範囲と計っていない区間
- **完成形の追加（発展）**：CAPA／8D（capa_actions、AI の下書きは人が採用したものだけ登録）、週次ダイジェスト（weekly_digests）、写真と vision、音声入力、関連マップ（/analysis/graph）、業務 Ontology の画面（/analysis/ontology）、マスタ管理（/settings/masters、FR-MA-02〜06）、回答の 👍/👎（chat_feedback、Langfuse のスコア）、画面幅 375〜1680px、報告書トリアージ（判断モデル Jev＋LangGraph、JEV_ENABLED=1 のときだけ。詳しくは 11_報告書トリアージ_JevとLangGraph.md）
- **判断モデルによる強化（2026-10-18）**：検索の並べ替え・質問の振り分け・引用の確かめ・帳票の読み取りの確かめ（FR-DM-01〜05、DECISIONS_ENABLED=1 のときだけ。詳しくは 14_判断モデルによる強化.md）。有効なとき、PDF・画像の取込の確信度は読み取りの確かめの結果で決める。AC-v50-15
- チャットで切る OpenCode の元からある道具に apply_patch・websearch・skill・question を足す（OpenCode v1.19.0 の名前。2026-10-13。v4.1 までは前の一覧のまま）
- MCP：完成形の追加で list_capa_actions・draft_capa_actions・create_capa_action・update_capa_action・generate_8d_report・generate_weekly_digest・preview_capa_update を足して **28本**

## 3. 正本の書き方（印）

- 印の無い行は、そのファイルが出てくる版からずっと入る
- ファイルの1行目に `<!-- file: v2.0 -->` と書くと、そのファイルは v2.0 から出てくる（無ければ v1.0 から）
- 1行だけ：行の終わりに `<!-- v3.0 -->`（v3.0 から）、`<!-- v1.0..v2.1 -->`（v1.0〜v2.1 だけ）。表の1行にも使える
- まとまり：印だけの行 `<!-- v1.1 -->` または `<!-- v1.0..v2.1 -->` で始め、印だけの行 `<!-- /v -->` で閉じる。入れ子にできる（両方の範囲が重なるところだけ入る）
- 版で値が変わるところ（道具の本数・サービスの数・DB の種類など）は、範囲つきの行を並べて書く。例：
  `- MCP の道具は15本 <!-- v2.0..v2.1 -->` と `- MCP の道具は17本 <!-- v3.0..v3.1 -->`
- 見出しにも印を付ける（その版に中身が無い見出しを残さない）。表は、見出し行と区切り行には印を付けず、中の行に付ける（その版で行が0になる表は、表ごとまとまりの印で囲む）
- 確かめ方：`python render_versions.py --check`（印の数と、版ごとの行数を出す）、`python render_versions.py --out <フォルダ>`（全版を書き出して読む）

## 4. 書くときの決まり

- 数字は110件の元データ（`data/defect_reports.csv`）とアプリのコードで確かめた値だけを書く。推測で書かない
- 例アプリに無いものは書かない。講座で必要だが例アプリに無いもの（数量の検査）は「例アプリには未実装」と書く
- 各版は、その時点のアプリの姿として読めるようにする（未来の機能を先に書かない。「第N回で足す」のような予告は書かない）
- 文体は既存の docs に合わせる（です・ます調ではなく、仕様書の言い切り）
