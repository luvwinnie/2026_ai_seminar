# DefectReport AI — バックエンド(FastAPI)

製造業 不良報告分析AI(セミナー完成イメージアプリ)の API サーバー。

## 構成

| パス | 役割 |
|---|---|
| `main.py` | FastAPI 本体。起動時に DB 初期化・CSV シード・マスタ投入・Chroma 索引構築(バックグラウンド)。`/mcp` に MCP サーバーをマウント |
| `database.py` | SQLAlchemy エンジン。`DATABASE_URL` があれば PostgreSQL、無ければ SQLite(受講者向けフォールバック) |
| `models.py` | テーブル定義(DefectReport / MasterItem / ChatSession / ChatMessage) |
| `schemas.py` | Pydantic スキーマ |
| `routers/` | REST API(reports / masters / ingest / dashboard / analysis / chat) |
| `services/llm.py` | 帳票AI抽出・4M分析(OpenCode 優先、Anthropic は任意の代替) |
| `services/opencode_client.py` | OpenCode サーバーのクライアント(ask / ask_json / stream) |
| `services/mcp_server.py` | MCP ツール9本(読取7+書込2)。OpenCode がチャット中に呼び出す |
| `services/rag.py` | Chroma ベクトル検索(multilingual-e5-small、キーワード検索フォールバック) |
| `services/stats.py` | ダッシュボード統計・p管理図・予兆アラート |
| `services/report_service.py` | 報告書の作成/更新/絞り込みの共通ロジック(REST と MCP で共用) |
| `tests/test_api.py` | 結合テスト(一時DBで実行) |

## ローカル起動(Docker なし)

```bash
# リポジトリルートで
python3 -m venv .venv
.venv/bin/pip install -r app/backend/requirements.txt
cd app/backend
../../.venv/bin/python -m uvicorn main:app --reload --port 8000
```

- 初回起動時に `data/defect_reports.csv`(模擬データ100件)が自動シードされる。
- AI機能(チャット・抽出・4M)を使うには OpenCode サーバーが必要(`app/opencode/` 参照)。
  API キーはリポジトリルートの `.env` に `OPENROUTER_API_KEY=sk-or-...` を設定。

## テスト

```bash
cd app/backend
../../.venv/bin/python -m pytest tests/ -v
```

## 主な環境変数

| 変数 | 既定値 | 説明 |
|---|---|---|
| `DATABASE_URL` | (なし=SQLite) | PostgreSQL 等の接続URL(Docker では compose が設定) |
| `DB_PATH` | `./data/defect_reports.db` | SQLite のファイルパス |
| `DATA_CSV` | `../../data/defect_reports.csv` | シード用CSV |
| `OPENCODE_URL` | (なし) | OpenCode サーバーURL(例 `http://localhost:4096`) |
| `OPENCODE_MODEL` | `anthropic/claude-sonnet-4.5` | OpenRouter のモデルID |
| `ANTHROPIC_API_KEY` | (なし) | 抽出/4M の代替経路(任意) |
| `EMBEDDINGS` | `on` | `off` でベクトル検索を無効化(キーワード検索になる) |

API 仕様は `docs/04_API設計書.md` を参照。
