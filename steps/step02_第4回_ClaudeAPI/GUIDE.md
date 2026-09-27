# 第4回 演習ガイド — Claude API の組み込み(AI 機能の中核)

> **この回の到達点コードは、このディレクトリの `backend/` `frontend/` にあります**(セミナー各回のスナップショット)。本ガイドは講師・受講者双方が手を動かすための手順書です。
>
> **この回のチャットは Claude API 直叩きで学びます**。完成形 `../../app` は発展としてチャットを OpenCode + OpenRouter + MCP に移行済みです(→ `../step05_第7回_仕上げ/README.md` の発展対応表)。

前提: 第3回(`../step01_第3回_土台`)の土台(一覧 API/画面・SQLite シード)が動いていること。API 仕様は `../../docs/04_API設計書.md`、Claude 利用設計は `../../docs/06_AI設計書.md` を参照。

---

## 1. この回の学習目標

セミナー企画書 第4回「Claude API の組み込み」に対応。

- **Claude API / SDK の呼び出しとメッセージ設計**(`anthropic` Python SDK)。
- **システムプロンプトと会話履歴の管理**。
- **ストリーミング応答**(SSE でトークンを逐次表示)。
- 【演習】アプリへの**チャット機能**の実装と、**構造化出力(JSON 抽出)**による帳票データの構造化。
- (発展)モデル提供元の選択肢: Claude API / OpenRouter / ローカル LLM(Ollama)。詳細は `../../docs/07_発展トピック.md`。

キーワード: Claude API / messages.stream / system prompt / 会話履歴 / SSE / 構造化出力(JSON Schema)。

---

## 2. 到達点(この回が終わると何が動くか)

- **チャット機能**が動く: `POST /api/chat/stream` が SSE(`token` → `done`)で応答し、フロントの `/chat` 画面に回答が**逐次ストリーミング表示**される。
- **会話履歴**(直近10往復)を踏まえて応答する。
- **構造化出力の演習**: Claude に JSON Schema を渡し、テキスト(帳票の文字列など)から `defect_reports` フィールドのサブセットを **JSON で抽出**できる(帳票ファイルの取り込み UI は第5回で完成)。
- API キー未設定時は AI 機能が無効化され、その旨が UI/`/health` の `anthropic_configured` でわかる。

> この回のチャットは、まだ RAG(報告書検索)を組み込まない「素のチャット」から始め、システムプロンプトと履歴管理・ストリーミングに集中します。RAG は第5回で足します。

---

## 3. ハンズオン手順

### 3-1. Claude Code の準備 / この回で使う機能

- **/model・/effort**: 実装は Sonnet、難所(SSE のデバッグ等)だけ `/effort` を上げる、といったコスト最適化。
- **/cost・/usage**: トークン消費を確認しながら進める。
- **CLAUDE.md 追記**: Claude API の利用規則(`../../docs/04` §7)を規約として書いておくと、Claude が誤ったパラメータを送るのを防げる。

**CLAUDE.md に追記すべき Claude API 規則(重要)**:
```
## Claude API 規則(docs/04 §7)
- SDK は anthropic(Python)。client = anthropic.Anthropic()
- モデルは env ANTHROPIC_MODEL(既定 claude-sonnet-5)。ハードコード禁止
- temperature / top_p / top_k / budget_tokens は送らない(Sonnet 5 では 400 になる)
- thinking はフィールド省略(既定 adaptive)
- チャットは client.messages.stream(...) + text_stream
- 構造化出力は output_config={"format":{"type":"json_schema","schema":...}}
- max_tokens: チャット 4096 / 抽出 4096
```

### 3-2. バイブコーディング プロンプト例

`../../docs/06_AI設計書.md` の (b)チャット・(a)構造化抽出のプロンプト設計と整合させます。

**プロンプト例1(SDK の疎通確認)**
```
anthropic SDK で Claude に「テスト」と送って応答を1回だけ受け取る最小の
Python スクリプトを app/backend に作って。モデルは env ANTHROPIC_MODEL
(既定 claude-sonnet-5)。temperature 等のパラメータは送らないこと(docs/04 §7)。
ANTHROPIC_API_KEY 未設定なら分かりやすいメッセージで終了して。
```

**プロンプト例2(ストリーミングのチャット API)**
```
POST /api/chat/stream を docs/04 §6 の仕様どおり実装して。
body は {"message": str, "history": [{"role","content"}]}(履歴は直近10往復に切り詰め)。
client.messages.stream() を使い、SSE で event: token(逐次 {"text":...})→ event: done を
送る。system プロンプトは「製造品質保証の専門AIアシスタント」。
まだ RAG は入れず、素のチャットでよい。max_tokens は 4096。
```

**プロンプト例3(フロントのストリーミング表示)**
```
/chat 画面を作って。入力欄と送信ボタン、会話の吹き出し表示。
送信したら POST /api/chat/stream を fetch のストリームで受け、event: token の text を
逐次追記表示して。event: done で完了。履歴は state で保持し、直近10往復を次のリクエストの
history に載せて。API キー未設定(/health の anthropic_configured=false)のときは
「AIチャットには APIキー設定が必要です」を表示して送信を無効化。
```

**プロンプト例4(構造化出力 = JSON 抽出の演習)**
```
帳票のテキスト(自由記述の不具合報告文)から docs/03 のフィールドを JSON で抽出する
関数を書いて。output_config の json_schema を使い、スキーマは docs/06 (a) の
EXTRACTION_SCHEMA に準拠(process と phenomenon は enum、日付は YYYY-MM-DD、
数値は数字のみ)。必須項目が欠けたら warnings に入れて confidence を落とす後処理も付けて。
まずはサンプル文字列でユニット的に動作確認できる形にして。
```

**プロンプト例5(システムプロンプトの検証)**
```
チャットのシステムプロンプトを2案作って、それぞれで同じ質問(「寸法不良が起きる
一般的な原因は?」)を投げて応答を比較して。より簡潔で製造現場向けに具体的な方を
採用理由とともに教えて。temperature は送らない前提で。
```

---

## 4. 動作確認方法

**チャット(非ストリーミング版でまず確認)** — docs/04 §6 のテスト用エンドポイント:
```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"こんにちは。何ができますか?","history":[]}'
```

**ストリーミング**(SSE がイベントごとに流れてくることを確認):
```bash
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"テスト","history":[]}'
# event: token ... が逐次、最後に event: done が来ればOK
```

**キー未設定の挙動**:
```bash
curl http://localhost:8000/health   # anthropic_configured が false であること
```

**フロント**: http://localhost:5173 の `/chat` で送信 → 文字が少しずつ表示される(逐次描画)こと。連続で質問して履歴が引き継がれること。

---

## 5. つまずきポイントと対処

| 症状 | 原因 | 対処 |
|---|---|---|
| API が 400(Bad Request) | `temperature` 等を送っている | Sonnet 5 では送らない(docs/04 §7)。リクエスト組み立てから該当パラメータを削除。 |
| 401/認証エラー | `ANTHROPIC_API_KEY` 未設定/誤り | `app/.env` を確認。SDK は環境変数を自動参照。 |
| ストリームが一括で出る(逐次にならない) | SSE のフラッシュ不足、フロントがまとめて読んでいる | バックは `text/event-stream` で都度 flush。フロントは `fetch` の `ReadableStream` を逐次 decode。 |
| SSE がフロントで途切れる | プロキシのバッファリング | 開発は Vite プロキシ、Docker は nginx。バッファ無効化を確認(docs/04 §8)。 |
| 履歴が長くなりすぎてコスト増 | 全履歴を毎回送信 | 直近10往復に切り詰める(docs/04 §6)。`/cost` で消費を確認。 |
| JSON 抽出が Schema に従わない | 自由生成になっている | `output_config` の json_schema を使う。enum を効かせて揺れを抑える(docs/06 (a))。 |
| モデル名エラー | モデルをハードコード | env `ANTHROPIC_MODEL`(既定 `claude-sonnet-5`)から取得。 |
