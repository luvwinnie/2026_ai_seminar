# 第5回 演習ガイド — データ連携・RAG・ツール活用(不適合報告書の取り込み)

> **この回の到達点コードは、このディレクトリの `backend/` `frontend/` にあります**(セミナー各回のスナップショット)。本ガイドは講師・受講者双方が手を動かすための手順書です。
>
> **この回の RAG チャットは Claude API 直叩きで学びます**。完成形 `../../app` は発展としてチャットを OpenCode + OpenRouter + MCP(9ツール)に移行済みです(→ `../step05_第7回_仕上げ/README.md` の発展対応表)。

前提: 第4回(`../step02_第4回_ClaudeAPI`)のチャット(SSE)と構造化出力が動いていること。設計は `../../docs/03`(Chroma)・`../../docs/04`(§3 取り込み・§6 チャット)・`../../docs/06`(RAG・抽出)を参照。

---

## 1. この回の学習目標

セミナー企画書 第5回「データ連携・RAG・ツール活用」に対応。

- **外部データの取り込み**: 不適合報告書(Excel / PDF / 画像)の読み込みと **OCR・構造化抽出**。
- **検索拡張生成(RAG)** の実装(ベクトル検索 + 根拠付き回答)。
- **Tool use(function calling)** による外部 API・関数の呼び出し(紹介・発展)。
- **MCP(Model Context Protocol)** の紹介と活用(`../../docs/07`)。
- 【演習】不良報告データを取り込み、チャットで**根拠付き回答(RAG)**を実現。

キーワード: Chroma / エンベディング(multilingual-e5-small)/ passage:・query: プレフィックス / vision(document・image ブロック)/ 構造化出力 / 引用 `[KZ25-XXXX]`。

---

## 2. 到達点(この回が終わると何が動くか)

- **Chroma ベクトル索引**が構築され、報告書登録時に upsert される(`../../docs/03` §3)。
- チャットが **RAG 化**: `POST /api/chat/stream` が回答前に `event: sources`(参照報告書)を出し、本文で `[KZ25-XXXX]` を引用する。
- **帳票アップロード AI 抽出**が動く: `POST /api/ingest/upload` に .xlsx / .pdf / .png / .jpg を送ると、Claude が項目を抽出して確認画面用に返す(**保存しない**)。`POST /api/ingest/confirm` で登録。
- 埋め込みが使えない環境では**キーワード検索フォールバック**(`search_mode: "keyword"`)で動作する。

---

## 3. ハンズオン手順

### 3-1. この回で使う Claude Code / 概念

- **データ連携**: `../../data/forms_xlsx/`(Excel 全件)・`../../data/forms_pdf/`(PDF 先頭10件)を取り込みデモに使う。
- **vision**: PDF は `document` ブロック、画像は `image` ブロックで base64 送信(`../../docs/04` §7)。
- **RAG の要点**: e5 は非対称モデル。**文書は `passage: `、クエリは `query: ` プレフィックス**を必ず付ける(`../../docs/03` §3、`../../docs/06` (b))。
- **/effort**: 抽出精度が出ないケースの調整で使う。**サブエージェント**で「抽出」と「RAG 検索」を分担調査するのも有効。

### 3-2. バイブコーディング プロンプト例

`../../docs/06` (a)(b)のプロンプト設計・スキーマと整合させます。

**プロンプト例1(Chroma 索引と upsert)**
```
docs/03 §3 のとおり Chroma(PersistentClient, app/backend/data/chroma)に
コレクション defect_reports を作って。ドキュメントは
"passage: {defect_description}\n原因: {cause}\n対策: {countermeasure}"、
id は defect_id、metadata は {defect_id, occurrence_date, machine_name, process,
phenomenon, severity, part_name, customer}。埋め込みは sentence-transformers の
intfloat/multilingual-e5-small。報告書の作成・更新時に upsert、削除時に delete するよう
CRUD に組み込んで。
```

**プロンプト例2(チャットの RAG 化)**
```
POST /api/chat/stream に RAG を組み込んで。ユーザーの質問を "query: " 付きで埋め込み、
Chroma で上位5件検索。回答前に event: sources として
[{defect_id, part_name, phenomenon, snippet, score}] を1回送る。
検索結果を文脈に組み立て、system プロンプトは docs/06 (b) の
「参考報告書の事実のみに基づき、参照は [KZ25-XXXX] 形式で引用」。
質問が集計系(何件・一番多い・率 等)なら SQL 集計結果も文脈に足して。
```

**プロンプト例3(キーワード検索フォールバック)**
```
sentence-transformers が import できない/モデルが無い環境では、
SQLite の LIKE 検索(defect_description・cause・part_name)にフォールバックして。
その場合レスポンス/メタに search_mode: "keyword" を明示し、/health の vector_search も
"keyword" を返すように。e5 が使えるときは "e5"。
```

**プロンプト例4(帳票アップロード抽出 — vision)**
```
POST /api/ingest/upload を docs/04 §3 のとおり実装して。multipart の file を受け、
xlsx は openpyxl でセル抽出 → Claude で構造化補正、pdf/画像は Claude vision
(pdf=document, 画像=image の base64 ブロック)+ 構造化出力で項目抽出。
返すのは {extracted, confidence, warnings, source_filename} で、保存はしない。
confidence 判定と warnings はサーバ後処理(docs/06 (a) の judge_confidence)。
ANTHROPIC_API_KEY 未設定なら pdf/画像は 503、xlsx はセル抽出のみ(confidence medium)。
```

**プロンプト例5(取り込み確認 UI と登録)**
```
/reports/new にファイルのドロップゾーンを作って。アップロード後、
/api/ingest/upload の extracted をフォームに反映し、confidence バッジ(high/medium/low)と
warnings を表示。ユーザーが修正して「登録」を押したら /api/ingest/confirm に送り、
成功したら詳細画面に遷移。data/forms_pdf/ のサンプルで一連の流れを試せるように。
```

---

## 4. 動作確認方法

**RAG チャット**(sources → token → done の順で SSE が来る):
```bash
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"GENOS M560-V の寸法不良の傾向と原因は?","history":[]}'
# 先頭に event: sources({"items":[{"defect_id":"KZ25-...",...}]})が出て、
# 本文に [KZ25-XXXX] の引用が含まれること
```

**検索モードの確認**:
```bash
curl http://localhost:8000/health   # vector_search が "e5" または "keyword"
```

**帳票アップロード**(サンプル PDF で抽出):
```bash
curl -X POST http://localhost:8000/api/ingest/upload \
  -F "file=@../../data/forms_pdf/KZ25-0001.pdf"
# {"extracted":{...},"confidence":"high|medium|low","warnings":[...],"source_filename":"KZ25-0001.pdf"}
```

**フロント**: `/reports/new` でサンプル帳票をドロップ → 抽出結果がフォームに入り、修正 → 登録 → 詳細表示。`/chat` で質問 → ソースカードが出て、本文に `[KZ25-XXXX]` が付く。

---

## 5. つまずきポイントと対処

| 症状 | 原因 | 対処 |
|---|---|---|
| RAG の精度が低い/無関係な引用 | プレフィックス漏れ | 文書 `passage:` / クエリ `query:` を必ず付ける(docs/03 §3)。 |
| 埋め込みでエラー/初回が重い | sentence-transformers 未導入、初回モデル DL | `requirements-embeddings.txt` を入れる。無理ならキーワード検索で継続(想定内)。 |
| sources が出ない | イベントの送信順が違う | 検索直後に `event: sources` を1回、その後 `token`(docs/04 §6)。 |
| PDF/画像抽出が 503 | APIキー未設定 | pdf/画像は vision 必須。xlsx はキー無しでもセル抽出のみ動く(docs/04 §3)。 |
| 抽出 JSON が崩れる | 構造化出力を使っていない | `output_config` の json_schema + enum を使う(docs/06 (a))。 |
| 日付/数値がバラバラ | 正規化不足 | system プロンプトで YYYY-MM-DD・数字のみを指示(docs/06 (a))。 |
| 登録しても検索に出ない | Chroma への upsert 漏れ | CRUD の作成/更新で必ず upsert、削除で delete(docs/04 §2)。 |
| Vector と DB の件数がズレる | 片方だけ更新 | 保存処理を1箇所にまとめ、SQLite と Chroma を同時に更新。 |
