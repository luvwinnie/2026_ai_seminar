# 第7回 演習ガイド — テスト・デバッグ・ドキュメント・デプロイ / UI の最終仕上げ

> **この回は専用のコードスナップショットを置かず、到達点は完成形 `../../app/` です**(仕上げ回)。完成形が step01〜04 からどう発展したかは本ディレクトリの `README.md`(発展対応表)を参照してください。本ガイドは講師・受講者双方が手を動かすための手順書です。

前提: 第6回(`../step04_第6回_KPI分析`)まででチャット・RAG・取り込み・ダッシュボード・4M・アラートが動いていること。設計は `../../docs/04`(§8 Docker)・`../../README.md`・全 `../../docs/` を参照。

---

## 1. この回の学習目標

セミナー企画書 第7回「テスト・デバッグ・ドキュメント・デプロイ / UI の最終仕上げ」に対応。

- **UI・機能の最終仕上げ**(入力フォーム・ファイルアップロード・結果表示、「バイブコーディング」での機能追加)。
- 【演習】Claude Code による**テストコードの生成と実行**。
- **デバッグの進め方**(エラーを貼って直す)。
- **README や仕様書の自動生成**。
- 【演習】**簡易デプロイ**(Docker Compose)と完成アプリのレビュー。

キーワード: pytest / Vitest / Docker Compose / nginx プロキシ / /code-review / README 自動生成 / CRUD 完成。

---

## 2. 到達点(この回が終わると何が動くか)

- **CRUD が完成**する: `POST /api/reports`(採番)・`PUT`(部分更新+Chroma 再 upsert)・`DELETE`(Chroma からも削除)が仕様どおり動く(`../../docs/04` §2)。
- **バックエンドのテスト(pytest)**が通る: CRUD・統計・アラート・(モックした)AI 系のテスト。
- **`docker compose up` の一括起動**が動く: フロント(nginx 配信)+ バック(uvicorn)、`/api`・`/health` のプロキシ、初回シード(`../../docs/04` §8)。
- **README・仕様書**が最新化される。
- 完成形として **`../../app/`** と同等の状態に到達する。

---

## 3. ハンズオン手順

### 3-1. この回で使う Claude Code / 概念

- **テスト生成**: 「この API のテストを pytest で書いて」と依頼。AI 呼び出し部分は**モック**して、キー無し・オフラインでも回るようにする。
- **/code-review**: 差分のバグレビュー(効力レベル指定可)。仕上げ前に一度かける。
- **/security-review**: 簡易な脆弱性チェック(発展)。
- **README・仕様の自動生成**: `/init` で CLAUDE.md、`README` はプロジェクト構成から生成・更新。
- **デバッグの基本**: エラーの stack trace やログを**そのまま Claude に貼る**。計画モードで直し方を確認してから適用。

### 3-2. バイブコーディング プロンプト例

`../../docs/04`(CRUD・Docker)、`../../README.md` と整合させます。

**プロンプト例1(CRUD の仕上げ)**
```
報告書の CRUD を docs/04 §2 のとおり完成させて。
POST は defect_id 未指定なら KZ25-<連番> を採番し、費用未指定なら total_cost をサーバ側で
合算、保存後に Chroma へ upsert、201 で Report を返す。
PUT は渡されたフィールドのみ部分更新して Chroma を再 upsert。
DELETE は SQLite と Chroma の両方から消して 204。存在しない ID は 404。
フロントの詳細画面に編集フォームと削除ボタン(確認ダイアログ付き)を追加して。
```

**プロンプト例2(バックエンドのテスト生成)**
```
app/backend の pytest を書いて。対象は reports の CRUD(作成→取得→更新→削除)、
GET /api/reports のフィルタ(status/severity/machine/date_from/date_to)、
/api/dashboard/statistics の件数一致、/api/analysis/alerts のルール。
Claude API と埋め込みは monkeypatch でモックし、APIキー無しでも通るようにして。
テスト用の一時 SQLite を使い、本番 DB を汚さないこと。
```

**プロンプト例3(フロントのテスト・仕上げ)**
```
入力フォームのバリデーションを仕上げて(必須項目、defect_count <= production_count、
severity/status はセレクト固定)。違反時は保存無効+赤表示。
Vitest で一覧のフィルタと新規作成フォームのバリデーションのユニットテストを書いて。
ローディングはスケルトン、エラーは Snackbar + 画面内メッセージ(docs/05 §6)。
```

**プロンプト例4(Docker Compose デプロイ)**
```
app/docker-compose.yml を docs/04 §8 のとおり用意して。
backend は python:3.12-slim で uvicorn main:app --host 0.0.0.0 --port 8000、
volume ./backend/data:/app/data、env に ANTHROPIC_API_KEY と ANTHROPIC_MODEL。
frontend は node:22 で build 後 nginx:alpine 配信(5173→80)、nginx で /api と /health を
backend:8000 にプロキシ。起動時に DB が空なら data/defect_reports.csv からシード +
Chroma 索引構築。docker compose up --build で両方立ち上がるようにして。
```

**プロンプト例5(README / 仕様の更新)**
```
実装後のディレクトリ構成と実際の起動手順に合わせて README を更新して。
機能一覧・技術スタック・セットアップ(venv+npm / docker compose up)・.env 設定・
模擬データ生成(python data/generate_mock_data.py)・セミナー対応表・docs 一覧を含めて。
docs/ の内容と矛盾がないか確認して。
```

**プロンプト例6(仕上げレビュー)**
```
/code-review をかけて、差分のバグと未処理のエラーケースを洗い出して。
特に APIキー未設定・埋め込み不在・データ0件の縮退動作(docs/02 のエラー時挙動)が
守られているか確認して。指摘は重要度順に整理して。
```

---

## 4. 動作確認方法

**テスト**:
```bash
cd app/backend && pytest -q          # 全テストが緑
cd app/frontend && npm run test      # Vitest(あれば)
```

**CRUD 一巡**(作成 → 更新 → 削除):
```bash
# 作成(採番される)
curl -X POST http://localhost:8000/api/reports -H "Content-Type: application/json" \
  -d '{"occurrence_date":"2026-04-01","customer":"翠峰重工業","process":"旋盤","machine_name":"QUICK TURN 250MSY","operator_name":"山田","part_number":"1234-567890-11","part_name":"シャフト","production_count":100,"defect_count":2,"defect_description":"外径公差外れ","phenomenon":"寸法不良","severity":"medium","status":"open"}'
# 返ってきた defect_id を KZ25-XXXX とする
curl -X PUT http://localhost:8000/api/reports/KZ25-XXXX -H "Content-Type: application/json" -d '{"status":"completed"}'
curl -X DELETE http://localhost:8000/api/reports/KZ25-XXXX   # 204
```

**Docker 一括起動**:
```bash
cd app && docker compose up --build
# http://localhost:5173 でフロント、http://localhost:8000/health でバック
curl http://localhost:8000/health    # reports 件数が入っていればシード成功
```

**レビュー**: `/dashboard`・`/reports`・`/chat`・`/alerts` を一通り操作し、`../../docs/02` のユースケース3本(現場の帳票取込 / QA の RAG→4M / 経営者の月次レビュー→アラート)が通しで動くことを確認。

---

## 5. つまずきポイントと対処

| 症状 | 原因 | 対処 |
|---|---|---|
| テストが APIキーを要求して落ちる | AI 呼び出しを実行している | Claude/埋め込みを monkeypatch でモック。ネットワークに出ない構成に。 |
| テストが本番 DB を書き換える | 固定 DB を参照 | テスト用の一時 SQLite(fixture)に差し替え、`app/backend/data` を汚さない。 |
| DELETE 後も検索に出る | Chroma から消していない | SQLite と Chroma の両方を削除(docs/04 §2)。 |
| PUT で他フィールドが消える | 全体置換している | 渡されたフィールドのみ部分更新(docs/04 §2)。 |
| Docker で `/api` が 404/502 | nginx プロキシ設定ミス | nginx で `/api`・`/health` を `backend:8000` へ。バックの起動完了を待つ。 |
| Docker 起動後データが空 | 初回シードが走っていない | 起動時に DB が空なら CSV からシード(docs/04 §8)。volume の権限も確認。 |
| フロントの build 失敗 | 型エラー | `tsc -b` のエラーをそのまま Claude に貼る。計画モードで修正方針を確認。 |
| SSE が Docker でだけ途切れる | nginx のバッファリング | プロキシのバッファ無効化(`proxy_buffering off` 等)。 |
| README と実装が食い違う | 手動更新漏れ | 実際の構成から README を再生成し、docs/ と突き合わせる。 |
