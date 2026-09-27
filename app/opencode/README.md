# DefectReport AI — OpenCode サービス

チャット・帳票AI抽出・4M分析の生成エンジン。[OpenCode](https://opencode.ai) をヘッドレス
(`opencode serve`)で起動し、[OpenRouter](https://openrouter.ai) 経由でモデルを呼び出す。

## ファイル

| ファイル | 役割 |
|---|---|
| `Dockerfile` | node:22-slim に `opencode-ai` をグローバルインストール |
| `entrypoint.sh` | 環境変数 `OPENROUTER_API_KEY` から `~/.local/share/opencode/auth.json` を生成して `opencode serve --hostname 0.0.0.0 --port 4096` を起動([OpenRouter 公式クックブック](https://openrouter.ai/docs/cookbook/coding-agents/opencode-integration)の方式) |
| `opencode.json` | プロバイダ(openrouter)と MCP サーバー(`defect-reports` → `http://backend:8000/mcp/`)の設定 |
| `AGENTS.md` | エージェントへの常設指示(ツール利用原則・書き込み安全規則・出力規約)。OpenCode がプロジェクト指示として自動で読み込む |

## 動作の仕組み

1. バックエンドが `POST /session` → `POST /session/{id}/prompt_async` でプロンプトを送信
2. OpenCode エージェントが OpenRouter のモデル(env `OPENCODE_MODEL`)で推論
3. 必要に応じて MCP ツール(報告書の検索・集計・登録・更新)をバックエンドに呼び返す
4. バックエンドは `GET /event`(SSE)を購読し、本文・思考・ツール実行を逐次フロントへ転送

## 注意

- **MCP ツールの一覧は OpenCode 起動時に取得される。** バックエンドのツール定義
  (`app/backend/services/mcp_server.py`)を変更したら `docker compose restart opencode` が必要。
- モデルの変更は `.env` の `OPENCODE_MODEL`(OpenRouter のモデルID、例
  `anthropic/claude-sonnet-4.5` / `openai/gpt-4o-mini` / `google/gemini-2.5-flash`)。
