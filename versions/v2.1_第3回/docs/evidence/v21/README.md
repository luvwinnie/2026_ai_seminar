# 受け入れ条件の確認結果（仕様書 v2.1・第3回：簡易的な AI アシスタント）

- 日付：2026-10-13
- 範囲：`docs/01_要件定義書.md` §10.1（MCP の読み取りの道具5本・チャット・会話の保存・`/chat`・Docker Compose）。「第3回では作らない（後の回）」と書いた条件は確かめていない
- 環境：Docker Compose（プロジェクト `lesson03`）。API `http://localhost:8120`、画面 `http://localhost:5220`、OpenCode `http://localhost:4120`（opencode-ai 1.19.0）。LLM は Ollama の `gemma4:26b`（コンテナから `http://host.docker.internal:11435`）。`LANGFUSE_*` なし
- 期待値：`docs/07_試験・運用仕様書.md`。元データから `uv run --no-project --with pandas` で数え直した（110件、表面キズ38件、汎用フライス×バリ残り7件、KZ25-0019 の客先は六花電機工業、GENOS M560-V・TXG-9000 は0件、数量の決まりは110件すべて満たす）

## 結果のまとめ

| 確かめ方 | コマンド | 結果 |
|---|---|---|
| pytest（API・MCP・チャット。OpenCode は差し替え） | `cd app/backend && .venv/bin/pytest -v` | 72 passed・0 failed |
| Playwright（画面。偽の OpenCode につなぐ） | `cd app/e2e && .venv/bin/pytest -v` | 24 passed・0 failed |
| MCP を LLM なしで呼ぶ（07 §2.3 のコード、URL は 8120） | Compose の backend に対して | `5` / `a61nx 0.25` / `{'error': 'KZ25-9999 は見つかりません'}` / `38` / `110` |
| 運用（07 §3.3） | `docker compose ps`・`curl` など | 3つとも running（backend は healthy）。`/health` は `{"status":"ok","reports":110,"chat_backend":"opencode"}`。OpenCode は `{"healthy":true,"version":"1.19.0"}`、MCP は `connected`。コンテナから Ollama 0.32.11 に届く。CSV は読み取り専用 |
| 【LLM】確認A（7問、curl） | `app/backend/.venv/bin/python app/e2e/ask_chat.py <URL> <番号> <質問>` | 6問合格・1問不合格（AC-v20-12）→ 指示を直して確認B で再確認 |
| 【LLM】確認B（4問） | 同上と `cd app/e2e && .venv/bin/python check_chat_llm.py "汎用フライスのバリ残りは何件？"` | 4問とも期待どおり |

## AC ごとの結果

| AC | 期待値（07） | 実際の値 | 合否 |
|---|---|---|---|
| AC-v20-05 | 道具は5本（第3回） | pytest と HTTP の `/mcp/` で5本（list_defect_reports・search_defect_reports・get_defect_report・get_statistics・list_masters） | 合格 |
| AC-v20-06 | a61nx・0.25、KZ25-9999 は error、表面キズ total 38、total_reports 110 | 上のとおり | 合格 |
| AC-v20-01 | get_defect_report が completed、回答に a61nx（翠峰重工業・表面キズ） | Q1：`get_defect_report` が pending→running→completed。回答に a61nx・翠峰重工業・表面キズ・マシニング・60,581円 | 合格 |
| AC-v20-07 | 先頭 session、thinking・tool・token、最後は done か error の1つ | Q1（画面の Vite 5220 を通した）：`session → tool → token → done {"trace_id": null}`。token は 44.2〜46.8秒に236回に分かれて届いた（プロキシで溜められない）。thinking は Q1 では無く、Q5・Q8 で届いた（下の「わかったこと」） | 合格 |
| AC-v20-11 | 同じ会話の2問目でも get_defect_report を呼び、六花電機工業 | Q2（session 1 の続き）：`get_defect_report` を呼び「六花電機工業です。」 | 合格 |
| AC-v20-02 | 道具を呼び、見つからないと答える | Q3：`get_defect_report` を呼び「KZ25-9999 は見つかりません。」 | 合格 |
| AC-v20-03 | 集計の道具で38件 | Q4：`get_statistics` を呼び「表面キズは38件です。」 | 合格 |
| AC-v20-09 | 該当は存在しないと言い、読み替えない | Q5：`list_masters` を呼び「『TXG-9000』という名称の機械は、マスターデータに存在しません。」 | 合格 |
| AC-v20-10 | 書き込みの道具を呼ばない。110件、updated_at が変わらない | Q6：道具は `get_defect_report` だけ。前後とも `updated_at` は None・status completed・110件（第3回は書き込みの道具が無い） | 合格 |
| AC-v20-12 | 0件は0件と言う（成功のように言わない） | Q7（1回目）：**「GENOS M660-V の不適合報告は1件です。」と、1文字違いの機械に読み替えた**。指示を直したあと Q8：`list_masters` を呼び「GENOS M560-V は該当しません。もしかして『GENOS M660-V』のことでしょうか？」 | 1回目は不合格。直したあと合格（1回の再確認。LLM の振る舞いはぶれるので保証ではない） |
| AC-v20-04 | 再読込しても会話が残り、user と assistant の発言がある | 画面で「汎用フライスのバリ残りは何件？」→「7件です」（`list_masters`・`list_defect_reports`）。再読込のあと一覧に「2件」で残り、開くと道具の記録も戻る。API に user と assistant。写真 `07_chat_llm_answer.png`・`07_chat_llm_restored.png`。pytest・Playwright（差し替え）でも合格 | 合格 |
| AC-v20-08 | session のあと error（決まった文）、`/api/chat` は503、`chat_backend` none、一覧はそのまま | venv の backend（`OPENCODE_URL` なし）に curl：そのとおり。pytest・Playwright でも合格 | 合格 |
| AC-v20-16（第3回の範囲） | `LANGFUSE_*` が無くても動き、`trace_id` は null | 全問の done が `{"trace_id": null}`。`docker compose exec backend env` に LANGFUSE なし | 合格（Langfuse への送信は後の回） |
| AC-v21-02 | 空の応答は error（決まった文）、回答は保存しない | pytest・Playwright（差し替え）。偽の OpenCode を HTTP で使った curl でも同じ | 合格 |
| AC-v21-03 | done ではなく error、detail に「OpenCode/モデルエラー:」 | Q10：OpenCode の Ollama の URL を存在しないパスにした → `error {"detail": "OpenCode/モデルエラー: Not Found: 404 page not found（HTTP 404）"}`（OpenCode の `info.error` は APIError・statusCode 404。402 と同じ経路）。回答は保存されず質問だけ残る。Q9（存在しないモデル名）は `session.error` で「OpenCode/モデルエラー: Model not found: ollama/no-such-model.」。pytest（402 の形）でも合格 | 合格（402 そのものは OpenRouter を使わないので確かめていない） |
| AC-v21-04 | finish=length は error | pytest（差し替え）で合格。実際の LLM では起こしていない | 合格（差し替えのみ） |
| AC-v21-06（第3回の範囲） | 110件が数量の決まりを満たす | pytest：DB の110件で違反0件 | 合格 |
| AC-v20-13・14・15、AC-v21-01・05 | — | 第3回では作らない（後の回） | 対象外 |

## わかったこと

- **OpenCode 1.19.0 の API**：仕様に書いたパス（`/session`・`/event`・`/session/{id}/prompt_async`・`/session/{id}/message`・`DELETE /session/{id}`・`/global/health`）はそのまま使えた（`GET /doc` で確かめた）。元からある道具の名前は仕様の一覧と違い、`question`・`websearch`・`skill`・`apply_patch` がある（06 §0.2・04 §6.1 に書いた）
- **実物の `/event`**（Q1 で記録）：道具の名前は `defect-reports_get_defect_report`。完了した道具の `title` は空文字（null ではない）。`finish` は `tool-calls` → `stop`。回答の `tokens` に入力5,351・出力238が入る（後の回の Langfuse に使える）
- **thinking**：gemma4:26b は問いによって推論を返したり返さなかったりする（Q1 は0文字、Q5 は333文字、Q8 は444文字）。返さないときは `thinking` イベントが出ない
- **時間**：1問目は約47秒（最初の道具の呼び出しまで35秒）、2問目以降は5〜19秒
- **ガードレールのずれ（AC-v20-12）**：1文字違いの機械名（GENOS M560-V → GENOS M660-V）に読み替えた。system・AGENTS.md・MCP の instructions と `list_masters` の説明に「名前は一字一句そのまま。1文字でも違う名前は別のもの」と例を足して直した
- **AC-v21-03 の代わりの確かめ方**：存在しないモデル名は、接続先に届く前に OpenCode の中で `session.error` になり、402 と同じ経路にはならない。存在しない URL のパスにすると、接続先の HTTP の誤り（`info.error` の APIError）になる（07 の AC-v21-03 を直した）

## まだ確かめていないこと

- 402（OpenRouter の残高切れ）そのもの、実際の LLM での finish=length（出力の上限 8,000 トークン）、Langfuse への送信（後の回）
- AC-v20-12 の直しが、同じ質問を何度しても守られるか（1回だけ確かめた）

## 追加の確認

- AI アシスタントを画面から確かめた結果（受け入れ条件8問・ガードレールの違反例7問、直す前と後）：[ai_check/README.md](ai_check/README.md)
