# DefectReport AI — API設計書

FastAPI バックエンド(`app/backend`、ポート 8000)。フロントエンド(Vite、ポート 5173)は開発時 `/api` と `/health` を 8000 へプロキシする。全レスポンスは JSON(SSE を除く)。フィールド名は `docs/03_データモデル設計書.md` に一致させる。

## 認証
なし(ローカル演習用)。

## 1. ヘルスチェック
- `GET /health` → `{"status": "ok", "reports": <件数>, "anthropic_configured": bool, "chat_backend": "opencode" | "none", "vector_search": "e5" | "keyword"}`
- `chat_backend`: **チャットは OpenCode のみ**。`OPENCODE_URL` 設定時は `opencode`、未設定なら `none`(チャットは 503)。§6 参照。
- `anthropic_configured`: 名称は歴史的経緯だが、実体は**帳票抽出・4M分析に使う AI バックエンドが設定済みか**を表す(`OPENCODE_URL` か `ANTHROPIC_API_KEY` のいずれかがあれば true)。§3・§5・§7 参照。

## 2. 報告書 CRUD — `/api/reports`

| メソッド/パス | 説明 |
|---|---|
| `GET /api/reports` | 一覧。クエリ: `q`(defect_id/part_number/part_name/defect_description の部分一致), `status`, `severity`, `machine`, `process`, `category_4m`, `date_from`, `date_to`, `limit`(既定50, 最大500), `offset`, `sort`(既定 `-occurrence_date`) → `{"total": int, "items": [Report]}` |
| `POST /api/reports` | 新規作成。defect_id 未指定なら採番(`KZ25-` + 連番)。登録後 Chroma へ upsert。→ 201 + Report |
| `GET /api/reports/{defect_id}` | 詳細(defect_rate 含む)。404 あり |
| `PUT /api/reports/{defect_id}` | 部分更新(渡されたフィールドのみ)。Chroma 再 upsert |
| `DELETE /api/reports/{defect_id}` | 削除(Chroma からも削除)→ 204 |

Report オブジェクト = テーブル全カラム + `defect_rate`(float, 0除算時 null)。

**マスタ自動登録**: 報告書の作成(`POST`)・更新(`PUT`)時、6マスタ対象カラム(`customer` / `process` / `machine_name` / `operator_name` / `phenomenon` / `factor`)の値がマスタ(`masters`)に未登録なら、該当カテゴリへ `is_active=true` で自動登録する。詳細は §2.5 と `docs/03_データモデル設計書.md`「テーブル: masters」を参照。

## 2.5 マスタ管理 — `/api/masters`

ドロップダウン選択肢を DB マスタ化して CRUD する。対象は6カテゴリ: `customer`(客先)/ `process`(発生工程)/ `machine`(使用機械)/ `operator`(作業者)/ `phenomenon`(現象分類)/ `factor`(要因)。`severity` / `status` / `category_4m` は固定列挙のためマスタ対象外。カテゴリと報告書カラムの対応は `docs/03`「テーブル: masters」を参照。

| メソッド/パス | 説明 |
|---|---|
| `GET /api/masters` | 全カテゴリのマスタをカテゴリ別にグルーピングして返す。各項目に使用件数を付与 → `{"customer": [Master], "process": [Master], ...}` |
| `GET /api/masters/{category}?active_only=` | 指定カテゴリの一覧。`active_only=true` で有効(is_active)のみ。並びは `sort_order`→`name` 昇順 → `[Master]` |
| `POST /api/masters/{category}` | 新規登録。body `{"name": str}` → 201 + Master。同一 `(category, name)` が既存なら **409** |
| `PUT /api/masters/{category}/{item_id}` | 更新。body `{"name"?: str, "is_active"?: bool}`。**name 変更(リネーム)時は、対応カラムを持つ既存報告書の値を新名称へ伝播更新**する → `{...Master, "updated_reports": int}`。リネーム先が同カテゴリの既存名と衝突する場合は **409** |
| `DELETE /api/masters/{category}/{item_id}` | 削除。使用中(`usage_count` > 0)なら **409**(無効化を促す)。未使用なら **204** |

- Master オブジェクト = `{id, category, name, sort_order, is_active, usage_count}`。不正なカテゴリ名は **404**。
- リネーム伝播の例: `customer` マスタの「翠峰重工業」→「Alpha社」変更で、`defect_reports.customer = '翠峰重工業'` の行がすべて 'Alpha社' に更新され、`updated_reports` に件数を返す。Chroma のメタデータに含まれるカテゴリ(machine / process / phenomenon / customer)は該当報告書を再 upsert する。
- 無効化(`is_active=false`)した名称は、新規入力時の候補(§後述フロント)から除外されるが、既存報告書の値・集計には影響しない。

## 3. 帳票取り込み — `/api/ingest`

| メソッド/パス | 説明 |
|---|---|
| `POST /api/ingest/upload` | multipart/form-data `file`(.xlsx / .pdf / .png / .jpg)。xlsx は openpyxl でラベルセルを走査して抽出(AI バックエンドがあれば構造化補正)。pdf/画像は AI バックエンドで vision + 構造化出力で項目抽出。→ `{"extracted": {<Reportフィールドのサブセット>}, "confidence": "high"|"medium"|"low", "warnings": [str], "source_filename": str}`。**保存はしない**(確認画面用) |
| `POST /api/ingest/confirm` | body = extracted を編集した Report フィールド群 → `POST /api/reports` と同処理で保存 |

- **AI バックエンド**: 抽出・4M分析は OpenCode(OpenRouter 経由)を優先し、`ANTHROPIC_API_KEY` があれば Anthropic 直叩きを代替として使う(§7)。OpenCode 経路は全ツール無効の純生成で JSON を返させる(§6 の `opencode_client.ask_json`)。
- AI バックエンド未設定(`OPENCODE_URL` も `ANTHROPIC_API_KEY` も無し)時、pdf/画像は 503 `{"detail": "AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)"}`。xlsx はセル抽出のみで返す(confidence: "medium"、warning 付き)。

## 4. ダッシュボード統計 — `/api/dashboard`

- `GET /api/dashboard/statistics?date_from=&date_to=` →
```json
{
  "kpi": {"total_reports": int, "total_defects": int, "total_production": int,
           "defect_rate": float, "fpy": float, "total_cost": float,
           "recurrence_rate": float, "open_count": int},
  "monthly_trend": [{"month": "2025-04", "reports": int, "defects": int, "production": int, "defect_rate": float}],
  "pareto_phenomenon": [{"name": str, "count": int, "ratio": float, "cumulative_ratio": float}],
  "by_machine": [{"name": str, "reports": int, "defects": int, "defect_rate": float, "total_cost": float}],
  "by_operator": [...同形...], "by_process": [...], "by_customer": [...],
  "by_4m": [{"name": "Man|Machine|Material|Method|未分類", "count": int}],
  "by_severity": [{"name": str, "count": int}]
}
```
- `GET /api/dashboard/control-chart?months=12` → p管理図: `{"items": [{"period": "2025-04", "n": int, "defects": int, "p": float, "ucl": float, "lcl": float}], "p_bar": float}`(UCL/LCL = p̄ ± 3√(p̄(1−p̄)/n)、LCL は 0 で下限クリップ)

## 5. 分析・AI — `/api/analysis`

| メソッド/パス | 説明 |
|---|---|
| `GET /api/analysis/alerts` | ルールベースの予兆アラート → `{"items": [{"level": "critical"|"warning"|"info", "title": str, "message": str, "related": {"machine"?: str, "phenomenon"?: str}}]}`。ルール例: 直近30日で不良率が全期間平均の1.5倍超の機械 / 同一現象×同一機械が直近60日に3件以上 / 再発フラグ付きが直近30日に発生 |
| `POST /api/analysis/4m/{defect_id}` | AI バックエンドで 4M 分類+改善提案。→ `{"category_4m": str, "factor": str, "reasoning": str, "improvements": [str]}`。結果は report の category_4m / factor / ai_improvement に保存。**生成エンジンは抽出と共通(§7): OpenCode 優先 → Anthropic 代替**。OpenCode 経路は `ask_json`(全ツール無効の純生成 + JSON パース)、Anthropic 経路は structured outputs(`output_config.format`)。`category_4m` は Man/Machine/Material/Method の4値に検証。未設定時は 503 `{"detail": "AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)"}` |

## 6. AIチャット(RAG) — `/api/chat`

- `POST /api/chat/stream` body: `{"message": str, "session_id": int | null}`。`session_id=null`(または未指定)なら**新規セッションを作成**(title=先頭メッセージの先頭30文字)。`history` フィールドは互換用に残るが**サーバーは使わない**(履歴は DB から直近20件をロードする、§6 実装)。
- レスポンス: SSE (`text/event-stream`)。イベント(この順):
  - `event: session` / `data: {"id": int, "title": str}`(**SSE 先頭**。既存/新規いずれも現在のセッションを通知)
  - `event: sources` / `data: {"items": [{"defect_id": str, "part_name": str, "phenomenon": str, "snippet": str, "score": float}]}`(回答前に1回)
  - `event: token` / `data: {"text": str}`(回答本文の逐次デルタ)
  - `event: thinking` / `data: {"text": str}`(推論テキストのデルタ)
  - `event: tool` / `data: {"name": str, "status": "pending"|"running"|"completed"|"error", "title": str|null}`(MCP ツール実行の進捗)
  - `event: done` / `data: {}`
  - `event: error` / `data: {"detail": str}`
- 実装: セッション取得/新規作成 → `session` 先出し → backend が Chroma で上位5件検索(+ 集計系キーワードなら KPI サマリを追加)→ `sources` 先出し → **DB から直近20件の履歴をロード**しユーザー発話を保存 → system prompt + 検索文脈+履歴+質問を1プロンプトに畳み込み → OpenCode で生成。生成後、assistant メッセージ(本文・`sources`・`tools`・`thinking`)を DB に保存する。
- 非ストリーミング版 `POST /api/chat` も提供(body 同一 → `{"answer": str, "sources": [...], "session_id": int}`。テスト用)。1問1答のブロッキング呼び出し(`opencode_client.ask`)を使い、履歴も同様に永続化する。

### 会話履歴 API — `/api/chat/sessions`

チャットの会話をセッション単位で保存・閲覧・削除する(テーブルは `docs/03` §2.6)。

| メソッド/パス | 説明 |
|---|---|
| `GET /api/chat/sessions` | セッション一覧(更新降順)。→ `[{"id": int, "title": str, "created_at", "updated_at", "message_count": int}]` |
| `GET /api/chat/sessions/{id}` | セッション詳細。→ `{"session": {id,title,created_at,updated_at,message_count}, "messages": [{"id","role","content","sources": [...]|null, "tools": [...]|null, "thinking": str|null, "created_at"}]}`。404 あり |
| `DELETE /api/chat/sessions/{id}` | セッション削除(メッセージも CASCADE 削除)→ 204。404 あり |

### バックエンド構成(OpenCode 一本化)

**チャットの生成エンジンは OpenCode のみ**(Anthropic フォールバックは廃止)。`GET /health` の `chat_backend` は `opencode` / `none` の2値。

| 条件 | `chat_backend` | 挙動 |
|---|---|---|
| `OPENCODE_URL` が設定されている | `opencode` | OpenCode サーバー経由で OpenRouter のモデルを使用 |
| `OPENCODE_URL` 未設定 | `none` | チャットは 503(stream は `error` イベント)`{"detail": "AIバックエンドが設定されていません(OPENCODE_URL / OPENROUTER_API_KEY)"}` |

- **接続**: OpenCode サーバー(Compose の `opencode` サービス、`opencode serve --port 4096`)へ HTTP で問い合わせる。プロバイダ/モデルは env `OPENCODE_PROVIDER`(既定 `openrouter`)/ `OPENCODE_MODEL`(既定 `anthropic/claude-sonnet-4.5`)、認証は `OPENROUTER_API_KEY`(entrypoint が `~/.local/share/opencode/auth.json` を生成)。
- **ツール**: チャットでは OpenCode 標準のコーディング系ツール(bash/edit/write/patch/read/glob/grep/list/webfetch/todowrite/todoread/task)を無効化し、MCP の `defect-reports` ツール(§6.5)のみ有効化する。backend が渡した文脈で不足する場合、OpenCode が MCP ツールを自律的に呼び出して検索・集計・登録・更新を行う。
- **ストリーミング**: `/api/chat/stream` は OpenCode の SSE(`GET /event`)を購読し(`POST /session/{id}/prompt_async` で開始)、本文デルタを `token`、推論デルタを `thinking`、ツール実行状況を `tool` として**逐次転送**する(実デルタ)。デルタが取れない環境では完了メッセージ(`GET /session/{id}/message`)から全文を回収して `token` を1回送出する保険を持つ。
- 回答前の `sources` は backend の Chroma 検索結果、`[KZ25-XXXX]` 引用規約は共通。

## 6.5 MCPサーバー — `/mcp/`

バックエンド自身が MCP(Model Context Protocol)サーバーを `/mcp/`(FastMCP の Streamable HTTP。`main.py` で `app.mount("/mcp", mcp_app)`)で公開し、報告書データへのアクセスを **11本のツール**として提供する(読み取り7本+書き込み2本+画面操作2本)。OpenCode はこの MCP に接続し、チャット中に必要なツールを自律的に呼び出す。作成・更新は REST と共通ロジック(`services/report_service.py`)を使う。

**読み取り(7本)**

| ツール | 主な引数 | 返り値(概要) |
|---|---|---|
| `list_defect_reports` | `machine? / process? / customer? / operator? / phenomenon? / severity? / status? / category_4m? / date_from? / date_to? / q? / limit`(既定20・最大100)`/ offset / sort`(既定 `-occurrence_date`) | 条件が明確な絞り込み一覧 → `{"total": int, "items": [要約(defect_rate 含む)]}`。値は完全一致 |
| `search_defect_reports` | `query: str`, `top_k`(既定5), `machine?`, `process?` | 内容が曖昧な類似検索。`[{defect_id, part_name, machine_name, process, phenomenon, snippet, score}]` |
| `get_defect_report` | `defect_id: str` | 指定報告書の全フィールド(§2 の Report、`defect_rate` 含む)。無ければ `{"error": ...}` |
| `get_statistics` | `date_from? / date_to?` | ダッシュボード統計(§4 の `statistics` と同形の KPI・パレート・各集計・トレンド・内訳) |
| `get_control_chart` | `months`(既定12) | p 管理図(§4 の `control-chart` と同形、UCL/LCL 付き) |
| `get_active_alerts` | (なし) | 予兆アラート一覧(§5 の `/api/analysis/alerts` と同形) |
| `list_masters` | `category?`(customer/process/machine/operator/phenomenon/factor、省略で全カテゴリ) | マスタの正確な表記確認 → `{カテゴリ: [{"name", "usage_count"}]}`(有効値のみ) |

**書き込み(2本)** — system prompt で「ユーザーが明示的に依頼した場合のみ」実行すると規定。

| ツール | 主な引数 | 挙動 |
|---|---|---|
| `create_defect_report` | 必須: `occurrence_date / customer / process / machine_name / operator_name / part_number / part_name / production_count / defect_count / defect_description / phenomenon / severity`、任意: `discoverer / good_condition / cause / factor / category_4m / countermeasure / notes` | 新規登録。`defect_id` を自動採番、`status="open"` 固定 → `{"created": true, "defect_id": "KZ25-XXXX"}`(失敗時 `{"created": false, "error": ...}`) |
| `update_defect_report` | `defect_id` + `status? / severity? / countermeasure? / cause? / factor? / category_4m? / notes? / good_condition?` | 渡した項目のみ部分更新(**変更可能なのはこの8項目のみ**)→ `{"updated": true, "defect_id", "changed": [...]}` |

- **OpenCode からの接続方法**: `opencode.json` の `mcp.defect-reports` に登録。`{"mcp": {"defect-reports": {"type": "remote", "url": "http://backend:8000/mcp/", "enabled": true}}}`(Compose 内のサービス名 `backend` を参照)。OpenCode 上のツール名は `defect-reports_<ツール名>`。
- `/mcp/` は OpenCode(および外部の MCP クライアント)向けの公開口。純生成が必要な抽出・4M分析(§3・§5)では、OpenCode 経路でも MCP を含む全ツールを無効化する。

## 7. AI 利用規約(実装規則 — OpenCode/OpenRouter が主、Anthropic は任意の代替)

チャット・帳票抽出・4M分析はいずれも **OpenCode(OpenRouter 経由)を主エンジン**とする。抽出・4M分析は `ANTHROPIC_API_KEY` があれば **Anthropic 直叩きを代替経路**として使える(チャットは OpenCode 専用)。バックエンド判定は `services/llm.ai_backend()`(opencode → anthropic → none)、チャットは `routers/chat.chat_backend()`(opencode → none)。

**OpenCode / OpenRouter 経路(主)**
- プロバイダ/モデルは env `OPENCODE_PROVIDER`(既定 `openrouter`)/ `OPENCODE_MODEL`(既定 `anthropic/claude-sonnet-4.5`)。認証は `OPENROUTER_API_KEY`。接続先は env `OPENCODE_URL`。
- クライアントは `services/opencode_client`:
  - `stream(system, prompt)` … チャット用。`GET /event` 購読 + `POST /session/{id}/prompt_async`。`token`/`thinking`/`tool` を yield(§6)。
  - `ask(system, prompt)` … チャット非ストリーミング。`POST /session/{id}/message` の全文を返す。
  - `ask_json(system, prompt, files?)` … 抽出・4M分析用。**全ツール無効の純生成**でスキーマをプロンプトに埋め込み、応答を JSON パース。失敗時は「JSON のみで返答」と1回だけ再依頼。PDF/画像は `files=[{mime, filename, b64}]` を FilePartInput `{"type":"file","mime","filename","url":"data:<mime>;base64,<b64>"}` として message に添付。
- モデルエラーは HTTP 200 の `info.error` に入るため、`opencode_client` 側で検知して `RuntimeError` にする。

**Anthropic 経路(抽出・4M分析の代替のみ)**
- SDK: `anthropic`(Python)。モデルは env `ANTHROPIC_MODEL`(既定 `claude-sonnet-5`)。
- `temperature` / `top_p` / `top_k` / `budget_tokens` は**送らない**(Sonnet 5 では 400)。thinking はフィールド省略(既定 adaptive)。
- 構造化抽出は `output_config={"format": {"type": "json_schema", "schema": ...}}`。
- vision: 画像は `{"type": "image", "source": {"type": "base64", ...}}`、PDF は `{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", ...}}`。
- max_tokens: 抽出 4096 / 4M分析 2048。

## 8. Docker Compose(app/docker-compose.yml)

**4サービス構成**(`db` / `backend` / `opencode` / `frontend`)。

- `db`: `postgres:16-alpine`。全データ(報告書・マスタ・チャット履歴)の正本。env: `POSTGRES_USER=app` / `POSTGRES_PASSWORD=app` / `POSTGRES_DB=defectreport`。volume `db-data:/var/lib/postgresql/data`。healthcheck は `pg_isready`。
- `backend`: python:3.12-slim ベース、`uvicorn main:app --host 0.0.0.0 --port 8000`。env: `DATABASE_URL=postgresql+psycopg://app:app@db:5432/defectreport`(→ Docker では PostgreSQL を使用)/ OPENCODE_URL(既定 `http://opencode:4096`)/ OPENCODE_MODEL / ANTHROPIC_API_KEY / ANTHROPIC_MODEL。`depends_on: db(healthy)`。volume: named volume `backend-data:/app/data`(DB(SQLite フォールバック時)/ Chroma 索引の永続化)+ `../data:/seed-data:ro`(シード用 CSV。Dockerfile で `DATA_CSV=/seed-data/defect_reports.csv`)。`env_file` で `../.env`(`example_app/.env`)と `./.env` を任意読込。`/mcp/` で MCP サーバーを公開。
- `frontend`: node:22 で build → nginx:alpine 配信(port 5173→80 map)。nginx は `/api` `/health` を backend:8000 へ proxy。
- `opencode`: `build: ./opencode`(OpenCode サーバー)。`opencode serve --port 4096`。`opencode.json` の `mcp.defect-reports`(type: remote, url `http://backend:8000/mcp/`)で backend の MCP に接続。env: OPENROUTER_API_KEY, OPENCODE_MODEL(既定 `anthropic/claude-sonnet-4.5`)。entrypoint が `OPENROUTER_API_KEY` から `~/.local/share/opencode/auth.json` を生成。`depends_on: backend(healthy)`。
- **DB は二段構え**: Docker Compose では `DATABASE_URL` が `db` を指すため **PostgreSQL** に保存。`DATABASE_URL` 未設定(Docker なしの venv 起動)なら **SQLite**(`app/backend/data/defect_reports.db`)にフォールバック。スキーマは同一(`docs/03` §1)。requirements に `psycopg[binary]`。
- 起動時に DB が空なら `data/defect_reports.csv` から自動シード+Chroma 索引構築。
- **チャットは OpenCode 専用**(`opencode` サービス必須)。`OPENCODE_URL` が無いとチャットは 503。帳票抽出・4M分析は OpenCode が無くても `ANTHROPIC_API_KEY` があれば代替動作する。
- ホスト公開ポートは env で変更可: `BACKEND_PORT`(既定 8000)/ `FRONTEND_PORT`(既定 5173)。主な環境変数: `OPENROUTER_API_KEY`(必須)/ `OPENCODE_MODEL` / `OPENCODE_PROVIDER` / `OPENCODE_URL` / `ANTHROPIC_API_KEY`(任意)/ `ANTHROPIC_MODEL` / `DATABASE_URL`(未設定=SQLite、`DB_PATH` で SQLite パス上書き)。


### 6.9 WebMCP: 画面操作ツールと UI イベント SSE(2026-09 追加)

チャットAIがブラウザ画面を直接操作するための仕組み。

| 構成要素 | 内容 |
|---|---|
| MCPツール `ui_navigate(page, q?, machine?, severity?, status?)` | 指定ページへ遷移。page=reports は URL クエリで絞り込み表示 |
| MCPツール `ui_open_report(defect_id)` | 報告書詳細 `/reports/KZ25-XXXX` へ遷移 |
| `GET /api/ui/events` | UIイベントの SSE。`event: ui` / `data: {action, path, reason}`。15秒毎に keep-alive |
| `services/ui_bus.py` | thread-safe な pub/sub(購読者0なら ツールがエラーを返す) |
| フロント `UiControlBridge` | SSE を購読して React Router で遷移。許可プレフィックスのみ。Snackbar で操作を利用者に明示。WebMCP 対応ブラウザでは `navigator.modelContext.registerTool` にも同ツールを登録 |

安全設計: 遷移のみでデータは変更しない。ツールは「見せて/開いて」等の明示依頼時のみ使用(instructions で指示)。


### 6.10 スマート検索 REST と ui_navigate のフィルタ拡張(2026-09 追加)

| 項目 | 内容 |
|---|---|
| `GET /api/reports/search` | 意味検索(ハイブリッド `rag.search`)。params: q(必須)/top_k(≤40)/machine?/process?(後段絞り込み)。`/{defect_id}` より前にルート定義 |
| `GET /api/reports` 拡張 | customer / operator / phenomenon フィルタを追加(build_report_query は既対応) |
| `ui_navigate` reports 拡張 | process / customer / operator / phenomenon / category_4m / sort / **mode="smart"**(qと併用で意味検索画面) |
| 期間フィルタUI | サマリー・分析3種・時系列に PeriodFilter(プリセット+日付+月数)。値の正本はURLクエリで、人間とAIが同じ状態を共有 |

### 6.11 A/B強化機能のAPI(2026-09 追加、docs/10 提案の実装)

- `GET /api/reports/{defect_id}/similar?top_k=5` — 類似事例サジェスト(A-1)。ハイブリッド検索(`services/hybrid.py`)で当該報告書の本文に似た過去報告を返す
- `GET /api/digests` / `POST /api/digests/generate?days=7` — 週次ダイジェスト(A-2)。KPI前週比・重大不良・アラートを決定論集計し、OpenCode があれば「AI所見」を追記した Markdown を保存・返却
- `GET/POST /api/capa` / `PATCH /api/capa/{capa_id}` — 是正処置 CAPA(A-3)。status は open → in_progress → effect_check → closed(closed には effect_note 必須)。overdue フィルタ対応
- `POST /api/capa/draft?defect_id=...` — 類似事例の対策から AI がドラフト(採用は人間/明示依頼のみ)
- `POST /api/capa/eight-d?defect_id=...` / `GET /api/capa/eight-d/{defect_id}` — 8D レポート生成・取得
- `GET/POST /api/reports/{id}/photos` / `DELETE .../photos/{photo_id}` / `POST .../photos/{photo_id}/analyze` — 不良写真の添付と vision による外観所見(B-4)。8MB 上限、jpg/png/webp
- アラート強化(B-5): `stats.alerts()` に急増(直近30日≥3件かつ前30日比2倍)・対策後30日以内の再発(critical)・3ヶ月連続上昇のルールを追加
- MCP は §6.5 の 11 本から 22 本へ拡張(get_similar_reports / CAPA 5本 / generate_weekly_digest / ui_new_report / ui_edit_report / ui_run_4m_analysis / ui_set_theme)。ui_navigate は digests・capa ページと reports のスマート検索(mode=smart)にも対応

### 6.12 RAG 事例の応用 第2弾(2026-09 追加)

- **関連マップ/GraphRAG層**: `GET /api/graph` — 全報告書の相互kNNグラフ(埋め込み再利用、無ければJaccard)。強い縁=相互選択。`services/graph.py` が検索にも `expand_scores`(α=0.25の1ホップ減衰伝播)を提供し、hybrid検索のRRF後に適用される
- **回答フィードバック**: `POST/GET /api/chat/feedback` — チャット回答への👍/👎+コメント。週次ダイジェストのKPI表に集計が載る
- **同義語自動生成**: `backend/scripts/build_synonyms.py` — コーパス語彙→LLM言い換え候補→**実在検証で採用/破棄**→`services/synonyms_generated.json`(hybrid が手書き辞書と併読)。実行は `docker compose exec backend python scripts/build_synonyms.py --apply`
- **ツール呼び出し評価**: eval/dataset に required_tools・uiカテゴリ(8)・multiturnカテゴリ(4)を追加。run_eval が tool_ok / false_claim(操作主張のみでui_*未呼び出し)を採点。空応答は明示エラー化(opencode_client)+評価側3回リトライ
- 既知の運用注意: OpenRouter残高不足時は 402(in-flight credits)で空応答・ツール未実行に見える症状になる。opencode.json で `limit.output: 8000` に制限済み

### 6.13 報告書トリアージ — `/api/triage`(2026-09-26 追加)

判断モデル Jev(型付きの判断＋確率)と LangGraph(流れ・承認待ち・再開)。詳細は `docs/11_報告書トリアージ_JevとLangGraph.md`。

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/triage/status` | `enabled` / `backend`(openrouter・typesafe・none)/ `model` / `thresholds` / `ledger` |
| POST | `/api/triage/preview` | body: `defect_description`(必須)・`cause`・`countermeasure`・`process`・`machine_name`・`part_name`。判断だけ返し、保存しない |
| POST | `/api/triage/reports/{defect_id}` | グラフを実行。`status` は `completed` か `waiting_approval`。404=報告書なし、502=判断モデルの失敗 |
| GET | `/api/triage/reports/{defect_id}` | 最新の結果(404=未判定) |
| POST | `/api/triage/runs/{run_id}/resume` | body: `approved`・`selected`(処置案の番号)・`note`。承認待ち以外は 409 |

結果の主な項目: `decisions`(項目ごとの `value`・`confidence` か `probability`・`accepted`・`source`=jev/llm/rule・`top`)、
`jev`(`model`・`calls`・`latency_ms`・`input_tokens`・`cost_usd`・`request_ids`)、`llm`、`conflicts`、`escalation`、`capa_draft`、`review`、`created_capa`、`route`。
`JEV_ENABLED=1` と判断モデルのキーが無いときは 503。MCP の道具は増やしていない(28本のまま)。

