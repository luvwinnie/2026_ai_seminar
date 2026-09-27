# ローカルLLM評価（2026-09-15）

**軽量モデルの全件評価・検証完了:** [最新HTMLレポート](light_20260915/report/report.html) / [条件と再現手順](light_20260915/README.md) / [検証記録](light_20260915/report/validation.json)。保存20GB以下の31タグを確認。通常APIで生成21タグ×50ケース、MTP版は代替APIで別途50ケースを実測した。残るLlama 3.2 Visionはモデル読込エラー。埋め込み7タグ×24問×2回、OCR専用1タグの画像3枚も実行済み。以下は前回の評価を再現するための説明。

完成レポート: [HTML](reports/20260915/report.html) / [Markdown](reports/20260915/report.md)。
HTML内で各モデル・設問を展開すると、回答本文・実ツールの引数と結果を読めます。

## 何を測るか

| 区分 | 問数 | 内容 |
|---|---:|---|
| 固定検索結果からのRAG回答 | 6 | 同一の上位5報告から、正しいID・機械・工程を回答。無関係なIDの引用も検査 |
| 最初のツール呼び出し | 8 | 名前、JSON Schema、引数。UI／更新を実行せず呼び出し生成を検査 |
| Ontology Q&A | 10 | 実MCPによる名前解決→条件別集計、関係探索、欠損、不存在、曖昧さ、CAPA変更プレビュー |

正解・固定文脈・ツール要件は `dataset.json`。業務DBの117報告を凍結した `snapshot.json` と
3報告・3CAPAの検証fixtureを別SQLite `benchmark.db` に用意しています。
本体アプリのDB・設定はベンチマークから変更しません。

`benchmark.py` は実際のアプリFastMCPを呼ぶ小さな独自ハーネスです。
OpenCodeそのものの測定は `validate_opencode.py` で分けて実行します。
いずれもLLMの本文に書かれた「呼び出した」という主張を実行の証拠にしません。

## 保存物

- `reports/20260915/model_summary.csv`: モデル別の値・形式・手順・時間・トークン速度。
- `reports/20260915/case_results.csv`: 全質問・回答・実ツール呼び出し・採点。
- `reports/20260915/model_inventory.csv`: 全43タグと主比較の選定理由。
- `runs/native_v1_20260915/`: 主比較の生出力とSHA256。準備用の `pilot_20260915`、中断した `native_20260915` は集計対象外。
- `runs/opencode_20260915/`: OpenCodeの追加検証。sessionのメッセージ・tool partも保存。
- `benchmark.db`: 検証専用DB。業務本体への取り込み用ではありません。
- `opencode_work/`: 追加検証専用設定。OpenRouterキーを使用せずOllamaだけを設定。

生出力の厳密採点ではJSONオブジェクトの型も要求します。`analyze.py` の補助分析は
単一要素配列だけを正規化し、形式違反と値の誤りを分けます。複数候補から正解だけを
選びません。この分析は初期の形式違反を見て追加したもので、元の生出力と採点は保存しています。
日本語の説明文全体を自動で意味採点したものでも、RAGASを実行した結果でもありません。

加えて、妥当な別解の監査後に `grounded()` を追加しました。これがレポートの「根拠付きQ&A」です。
集計では指定scopeと実出力のmetricsを照合し、曖昧名では候補の実取得、CAPAからの関連先取得では
実キーと取得順序を照合します。固定した検索語・ツール経路と完全一致しなくても、同じ対象の根拠を
正しく取得した場合を別指標で評価します。元の `score`・規定手順の採点は変更していません。
`reports/20260915/analysis_metadata.json` に事後分析のルール名とコードSHAを記録しています。

## 再集計（LLMを呼ばない）

`example_app` ディレクトリで実行します。

```bash
.venv/bin/python eval/local_llm/analyze.py
.venv/bin/python -m pytest eval/local_llm/test_scoring.py eval/local_llm/test_analysis.py -q
```

検索方式の比較は `benchmark_retrieval.py`、起動エラーと出力上限の追加診断は
`diagnose_models.py`。いずれも元の主比較を差し替えず、独立したJSONに記録します。
OpenCodeの個別結果は `reports/20260915/opencode_cases.csv` にも集計します。

追加の集計依存は `matplotlib` と `markdown`。実測環境のPythonパッケージバージョンは
`environment.json` に保存します。

## 同じ24問を再実行

Ollama が必要です(接続先は環境変数 `OLLAMA_BASE_URL`、例 `http://localhost:11434`)。主比較は20モデルを**逐次**実行します。
既存データのモデル名を使い、クラウド転送モデルは選びません。
既存結果を上書きしない別出力先を指定してください。

```bash
.venv/bin/python eval/local_llm/benchmark.py --output runs/retest_local
```

モデルを絞る場合:

```bash
.venv/bin/python eval/local_llm/benchmark.py --models 'gemma4:31b,gpt-oss:20b' --output runs/retest_two
```

中断再開は同じ設定・データ・コードのSHAが一致するときに限ります。

```bash
.venv/bin/python eval/local_llm/benchmark.py --output runs/retest_two --models 'gemma4:31b,gpt-oss:20b' --resume
```

`analyze.py` の集計対象は `runs/native_v1_20260915` に固定しています。
別実行を比べる場合はその定数と出力先を別名にし、2026-09-15の結果と混ぜないでください。
`prepare.py` は稼働アプリの検索をやり直すため、既存datasetの再作成は同一試験の再実行には不要です。

## OpenCodeの追加検証

主比較が完了してから実行します。同じGPUへの同時推論を避けるため、完了フラグを確認するガードがあります。
検証専用MCPを別ターミナルで起動:

```bash
.venv/bin/python eval/local_llm/serve_mcp.py
```

Docker Desktop for Macの `host.docker.internal` から127.0.0.1:8766へ接続する構成です。
別のOSでは接続先を調整してください。以下のコンテナは今回の検証専用です。

```bash
docker run -d --name seminar-llm-bench-opencode-20260915 --entrypoint opencode \
  -p 127.0.0.1:4097:4096 \
  -v "$(pwd)/eval/local_llm/opencode_work":/work \
  app-opencode serve --hostname 0.0.0.0 --port 4096

.venv/bin/python eval/local_llm/validate_opencode.py --resume
.venv/bin/python eval/local_llm/analyze.py
```

コンテナの既存イメージで実測したバージョンは1.18.28です。`app-opencode` をビルドし直すと
バージョンが変わる可能性があります。測定終了後は検証専用コンテナを停止・削除し、MCPのターミナルをCtrl+Cで終了します。

```bash
docker stop seminar-llm-bench-opencode-20260915
docker rm seminar-llm-bench-opencode-20260915
```

## 解釈上の制約

各設問1試行の小規模テストです。結果はこの日本語の製造品質アプリ、プロンプト、ツール定義、
時間・出力制限に対する成績です。汎用的なモデル能力順位や、本番での成功率の保証にはしません。
モデル自体の違いに加え、呼び出し互換性、プロンプト遵守、thinking設定、実行ハーネスも影響します。
特にO07などでは「必要な確認を質問する」だけでなく「実際に解決ツールで確認する」手順を要求します。
