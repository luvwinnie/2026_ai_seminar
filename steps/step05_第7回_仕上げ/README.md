# 第7回 仕上げ — 到達点コードについて

この回の到達点コードは、**完成形の `../../app`** です。第7回では新しい機能を足すのではなく、
テスト整備・Docker 化・デプロイなど「仕上げ」を行うため、この回専用のコードスナップショットは置いていません。

- 完成形バックエンド: [`../../app/backend`](../../app/backend)
- 完成形フロントエンド: [`../../app/frontend`](../../app/frontend)
- 演習手順は本ディレクトリの `GUIDE.md` を参照してください。

各回の到達点(積み上げ):

| 回 | ディレクトリ | 到達点 |
|---|---|---|
| 第3回 | `../step01_第3回_土台` | 土台(一覧 API/画面・SQLite シード) |
| 第4回 | `../step02_第4回_ClaudeAPI` | + 素のチャット(SSE)・構造化出力 |
| 第5回 | `../step03_第5回_RAG取込` | + RAG・帳票取り込み |
| 第6回 | `../step04_第6回_KPI分析` | + ダッシュボード・分析(ほぼ完成形) |
| 第7回 | **本ディレクトリ** | 仕上げ(テスト・Docker)= `../../app` |

---

## テスト実行(完成形 app)

バックエンドの結合テスト(pytest)は完成形 `app/backend` にあります。リポジトリ直下の
`.venv` を用いて実行します(一時DBを使うため開発データには触れません)。

```bash
cd ../../app/backend
../../.venv/bin/python -m pytest tests/test_api.py -q
```

## Docker Compose 起動(完成形 app)

`app/docker-compose.yml` は **db / backend / opencode / frontend の4サービス**を起動します(DB は PostgreSQL、チャットは OpenCode 経由)。

```bash
cd ../../app
cp .env.example .env   # OPENROUTER_API_KEY を設定(チャット・抽出・4M に必要)
docker compose up --build
```

- フロント: http://localhost:5173
- バックエンド health: http://localhost:8000/health
- 必須キー: `OPENROUTER_API_KEY`(全AI機能)。`ANTHROPIC_API_KEY` は任意(抽出/4M の代替経路)。
- 停止: `docker compose down`(データを消す場合は `docker compose down -v`)

## ローカル開発起動(Docker を使わない場合)

```bash
# バックエンド(8000)
cd ../../app/backend
../../.venv/bin/python -m uvicorn main:app --reload --port 8000

# フロントエンド(5173、/api・/health は 8000 へプロキシ)
cd ../../app/frontend
npm install
npm run dev
```

---

## 完成形はここからさらに発展している

`steps/step01`〜`step04` のコードは**セミナー各回の到達点そのまま**で正しい状態です。とくに**チャットは第4回時点の Claude API 直叩き**(素のチャット+構造化出力)で学びます。完成形 `../../app` は、その後の発展として次を実装済みです(各回のステップコードには含みません)。

| # | 発展項目 | 内容 | 完成形での実装参照 |
|---|---|---|---|
| a | チャットの OpenCode 化 | チャット生成を **OpenCode + OpenRouter** に移行し、報告書データへは **MCP ツール9本**でアクセス(第4回の Claude API 直叩きから発展) | `../../app/opencode/`, `../../app/backend/services/opencode_client.py`, `../../app/backend/services/mcp_server.py`, `../../app/backend/routers/chat.py` |
| b | チャット履歴(セッション)永続化 | 会話をセッション単位で保存・一覧・復元・削除(リロード後も保持) | `../../app/backend/models.py`(ChatSession/ChatMessage), `../../app/backend/routers/chat.py`, `../../app/frontend/src/pages/Chat.tsx` |
| c | マスタ管理 | ドロップダウン選択肢(客先/工程/機械/作業者/現象/要因)を DB マスタ化して CRUD、リネームを既存報告書へ伝播、freeSolo Autocomplete でその場登録 | `../../app/backend/routers/masters.py`, `../../app/backend/services/report_service.py`, `../../app/frontend/src/pages/`(マスタ管理画面) |
| d | DB 二段構え(PostgreSQL/SQLite) | Docker では PostgreSQL、ローカル venv では SQLite に自動フォールバック(同一スキーマ) | `../../app/backend/database.py`, `../../app/docker-compose.yml`(`db` サービス) |
| e | ライト/ダークテーマ | 「CNCコックピット」テーマで両モード対応(サイドバー下部トグル、`prefers-color-scheme` 初期値、`localStorage` 永続化) | `../../app/frontend/src/theme.ts`, `../../app/frontend/src/ColorModeContext.tsx`, `../../app/frontend/src/colorMode.ts` |

各項目の仕様は `../../docs/01`〜`../../docs/06` に反映済み(チャット=§6、履歴=`docs/03` §2.6・`docs/04` §6、マスタ=FR-MA・`docs/04` §2.5・`docs/02` F7、DB=`docs/03` §1、テーマ=`docs/05` §5)。
