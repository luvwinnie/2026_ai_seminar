# DefectReport AI（演習用）

製造業の不適合報告書（模擬データ110件）を、一覧と詳細で探し、AI アシスタント（`/chat`）に聞ける Web アプリ。仕様は `docs/`（v2.1）が正本。
第3回は「簡易的な AI アシスタント」まで作る（MCP の読み取りの道具5本・チャット・会話の保存。書き込み・画面の操作・業務 Ontology・AI パネルは後の回。`docs/01_要件定義書.md` §10.1）。

- `app/backend` … FastAPI・SQLAlchemy 2.0・Pydantic v2（API、ポート **8120**）
- `app/frontend` … Vite・React・TypeScript・MUI・React Router（画面、ポート **5220**）
- `app/backend/services` … AI 関係：MCP サーバー（`/mcp/`、道具5本）・OpenCode の呼び出し・共通の読み取りの処理
- `app/opencode` … OpenCode（`opencode serve`、npm `opencode-ai` 1.19.0）の Dockerfile・`opencode.json`・`AGENTS.md`
- `app/e2e` … Playwright（Python）による画面のテスト

この PC では、仕様書のポート 8000（API）・5173（画面）・4096（OpenCode）を 8120・5220・4120 に読み替える。LLM はローカル LLM（Ollama の `gemma4:26b`。この PC からは `http://localhost:11435`、コンテナからは `http://host.docker.internal:11435`）。

## 前提

- [uv](https://docs.astral.sh/uv/)（Python 3.12 を uv で使う）
- Node.js 22 と npm
- Docker（Compose v2）。AI アシスタントを使うとき

## 初回の準備

リポジトリの直下で実行する。

```bash
# backend
uv venv app/backend/.venv --python 3.12
uv pip install -r app/backend/requirements.txt --python app/backend/.venv

# frontend
cd app/frontend && npm install && cd ../..

# 画面のテスト（使うときだけ）
uv venv app/e2e/.venv --python 3.12
uv pip install -r app/e2e/requirements.txt --python app/e2e/.venv
# ブラウザが無いときだけ（~/Library/Caches/ms-playwright に入る）
app/e2e/.venv/bin/playwright install chromium-headless-shell
```

## Docker Compose で起動（第3回から。AI アシスタントも使える）

backend・frontend・opencode の3つをまとめて起動する（プロジェクト名 `lesson03`）。リポジトリの直下で実行する。

```bash
docker compose up -d --build     # 作って起動（opencode は backend が healthy になってから起動する）
docker compose ps                # 3つとも running、backend は healthy
docker compose logs -f backend   # ログ（opencode・frontend も同じ）
docker compose stop              # 止める（コンテナを消すときは docker compose down）
```

ブラウザで http://localhost:5220/chat を開く（一覧は http://localhost:5220/reports）。

- `docker compose down -v` は使わない（DB のボリューム `db` が消える）。
- MCP の道具を変えたら `docker compose restart opencode`（OpenCode は起動したときに道具の一覧を読む）。
- 動作の確認：`curl -s localhost:8120/health` → `{"status":"ok","reports":110,"chat_backend":"opencode"}`、`curl -s localhost:4120/mcp` → `{"defect-reports":{"status":"connected"}}`
- 設定は `.env`（`.env.example` を写す。git に入れない）。今回は値の要るキーは無い。

## venv と npm で起動（v1.1 の形）

ターミナルを2つ使う。`OPENCODE_URL` を付けないときは、チャットは「AIバックエンドが設定されていません」になる（一覧・詳細はそのまま動く）。

```bash
# 1つ目：backend（http://localhost:8120）
cd app/backend
.venv/bin/uvicorn main:app --port 8120
```

```bash
# 2つ目：画面（http://localhost:5220）。/api と /health は 8120 へ転送する
cd app/frontend
npm run dev
```

ブラウザで http://localhost:5220/reports を開く。

- 空の DB で起動すると、`data/defect_reports.csv` の110件を入れ、続けてマスタ6種（79件）を作る。2回目からは入れ直さない。
- 動作の確認：`curl -s localhost:8120/health` → `{"status":"ok","reports":110}`
- 止めるときは、それぞれのターミナルで Ctrl+C。
- AI も使うときは、OpenCode を Compose と同じイメージのコンテナで動かし（PC のホームに設定を書かないため）、backend に `OPENCODE_URL=http://localhost:4120` を付けて起動する：

```bash
docker build -t lesson03-opencode app/opencode
docker run --rm -p 127.0.0.1:4120:4096 --add-host host.docker.internal:host-gateway \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11435 \
  -e DEFECT_REPORTS_MCP_URL=http://host.docker.internal:8120/mcp/ lesson03-opencode
cd app/backend && OPENCODE_URL=http://localhost:4120 OPENCODE_MODEL=ollama/gemma4:26b .venv/bin/uvicorn main:app --port 8120
```

### 環境変数（任意）

| 変数 | 既定 | 意味 |
|---|---|---|
| `DB_PATH` | `app/backend/data/defect_reports.db` | SQLite のファイル |
| `DATA_CSV` | `data/defect_reports.csv` | 空の DB に入れる模擬データ |
| `DATABASE_URL` | （なし） | 設定すると `DB_PATH` の代わりにこの DB を使う |
| `OPENCODE_URL` | （なし） | OpenCode（`opencode serve`）の URL。無いとチャットは使えない（`chat_backend` が `none`） |
| `OPENCODE_MODEL` | `anthropic/claude-sonnet-4.5` | 使うモデル。この PC では `ollama/gemma4:26b` |
| `OLLAMA_BASE_URL` | （なし） | OpenCode が読む Ollama の URL（`/v1` は付けない） |
| `LANGFUSE_*` | （なし） | 第3回は Langfuse へ送らない（後の回）。無くても動き、`trace_id` は null |

### DB を作り直す

列を変えたときなどは、backend を止めて DB ファイルを消し、起動し直す（報告書は CSV から入れ直される）。

```bash
rm app/backend/data/defect_reports.db
```

## テスト

```bash
# API・MCP の道具・チャット（pytest）。一時ファイルの DB を使い、OpenCode は差し替える（LLM を呼ばない）
cd app/backend && .venv/bin/pytest -v

# 画面（Playwright）。偽の OpenCode・backend・画面をテストが自分で起動して止める（LLM を呼ばない）。
# 8120・5220 を使うので、手で起動したサーバーは先に止めておく
cd app/e2e && .venv/bin/pytest -v
```

テスト名には、受け入れ条件の番号（`docs/07_試験・運用仕様書.md` の AC-xx）を入れている（例：`test_AC_v10_03_machine_a61nx`）。
