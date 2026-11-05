# DefectReport AI（演習用）

製造業の不適合報告書（模擬データ110件）を、一覧と詳細で探す Web アプリ。仕様は `docs/`（v1.1）が正本。

- `app/backend` … FastAPI・SQLAlchemy 2.0・Pydantic v2（API、ポート **8110**）
- `app/frontend` … Vite・React・TypeScript・MUI・React Router（画面、ポート **5210**）
- `app/e2e` … Playwright（Python）による画面のテスト

この PC では、仕様書のポート 8000（API）・5173（画面）を 8110・5210 に読み替える。Docker は使わない。

## 前提

- [uv](https://docs.astral.sh/uv/)（Python 3.12 を uv で使う）
- Node.js 22 と npm

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

## 起動

ターミナルを2つ使う。

```bash
# 1つ目：backend（http://localhost:8110）
cd app/backend
.venv/bin/uvicorn main:app --port 8110
```

```bash
# 2つ目：画面（http://localhost:5210）。/api と /health は 8110 へ転送する
cd app/frontend
npm run dev
```

ブラウザで http://localhost:5210/reports を開く。

- 空の DB で起動すると、`data/defect_reports.csv` の110件を入れ、続けてマスタ6種（79件）を作る。2回目からは入れ直さない。
- 動作の確認：`curl -s localhost:8110/health` → `{"status":"ok","reports":110}`
- 止めるときは、それぞれのターミナルで Ctrl+C。

### 環境変数（任意）

| 変数 | 既定 | 意味 |
|---|---|---|
| `DB_PATH` | `app/backend/data/defect_reports.db` | SQLite のファイル |
| `DATA_CSV` | `data/defect_reports.csv` | 空の DB に入れる模擬データ |
| `DATABASE_URL` | （なし） | 設定すると `DB_PATH` の代わりにこの DB を使う |

### DB を作り直す

列を変えたときなどは、backend を止めて DB ファイルを消し、起動し直す（報告書は CSV から入れ直される）。

```bash
rm app/backend/data/defect_reports.db
```

## テスト

```bash
# API（pytest）。一時ファイルの DB を使う
cd app/backend && .venv/bin/pytest -v

# 画面（Playwright）。backend と画面をテストが自分で起動して止める。
# 8110・5210 を使うので、手で起動したサーバーは先に止めておく
cd app/e2e && .venv/bin/pytest -v
```

テスト名には、受け入れ条件の番号（`docs/07_試験・運用仕様書.md` の AC-xx）を入れている（例：`test_AC_v10_03_machine_a61nx`）。
