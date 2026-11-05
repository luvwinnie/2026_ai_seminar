# DefectReport AI（演習用）

## 作業のルール
- 日本語で説明する。
- data/ の CSV と Excel（data/不適合報告書/）は読み取り専用の原本として扱い、変更・移動しない。
- このフォルダの外のファイルを読まない・変えない。
- 調べた結果は、確認できた値と推測を分け、ファイル名・件数を示す。
- 仕様書（docs/）が正本。仕様と違う作り方をするときは、先に仕様書を直してから作る。
- 実行したコマンドと確認結果を示す。未確認のことを確認済みとして書かない。

## この PC の決まり
- Python は uv で使う（uv venv・uv pip・uv run --with …）。Node.js は 22。
- ポート：API は 8120、画面は 5220（仕様書の 8000・5173 は、この PC では別のアプリが使っているので読み替える。第2回の版は 8110・5210 を使う）。
- 起動したサーバーは、作業の最後に止める。

## 作るときのルール
- 構成：app/backend（FastAPI）、app/frontend（React）、docs/（仕様書）。
- テストは app/backend/tests に pytest で書き、受け入れ条件の ID（AC-xx）をテスト名に入れる。
- 変更したらテストを実行し、件数と passed/failed を報告する。
- 秘密の値（API キー）は .env に置き、コード・ログ・画面に出さない。

## 第3回からの決まり（Docker・LLM）
- 第3回から Docker Compose で動かす（backend・frontend・opencode）。Compose のプロジェクト名は lesson03。
- この PC で外に出すポート：API は 8120、画面は 5220、OpenCode は 4120（仕様書の 8000・5173・4096 はコンテナの中の番号として使ってよい）。
- `docker compose down -v` は使わない（データが消える）。このフォルダの Compose 以外のコンテナには触らない。
- LLM はローカル LLM（Ollama）を使う。この PC からは `http://localhost:11435`、コンテナからは `http://host.docker.internal:11435`（講師が研究室のサーバーへつないである。OpenAI 互換は `/v1`）。モデルは gemma4:26b。
- OpenRouter のキーは置いていない（今回は使わない）。OpenCode に付いている無料モデル（opencode プロバイダ）も使わない。
- 実際に LLM を呼ぶ確認は、1回の確認で10問まで。
- OpenCode は npm の opencode-ai を版を固定して入れる（1.19.0）。
