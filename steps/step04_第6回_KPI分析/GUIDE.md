# 第6回 演習ガイド — データサイエンス実践:不良データ分析と KPI ダッシュボード

> **この回の到達点コードは、このディレクトリの `backend/` `frontend/` にあります**(セミナー各回のスナップショット)。本ガイドは講師・受講者双方が手を動かすための手順書です。
>
> この回で扱うチャットは第4回時点の Claude API 直叩きのままです。完成形 `../../app` は発展としてチャットの OpenCode 化・チャット履歴永続化・マスタ管理・PostgreSQL 対応・ライト/ダークテーマを実装済みです(→ `../step05_第7回_仕上げ/README.md` の発展対応表)。

前提: 第5回(`../step03_第5回_RAG取込`)まででデータ・RAG・取り込みが動いていること。設計は `../../docs/04`(§4 統計・§5 分析/アラート)・`../../docs/05`(ダッシュボード画面)・`../../docs/06`(4M 分析)を参照。

---

## 1. この回の学習目標

セミナー企画書 第6回「データサイエンス実践」に対応。

- **製造業データ分析の基礎**: 製造 KPI(不良率・直行率 FPY・OEE・MTBF/MTTR)と QC 七つ道具(パレート図・ヒストグラム・管理図)。
- **4M 分析(Man/Machine/Material/Method)** による根本原因の分類・集計。
- 【演習】pandas による集計と、**パレート図・管理図・トレンド分析**(Claude に分析コードを生成させる「バイブ・アナリティクス」)。
- 【演習】**KPI ダッシュボード**の実装(不良件数・不良率・機械別/担当者別集計・トレンドのグラフ化)。
- **UI の仕上げ**: Claude Design・Figma 連携(MCP)による高品質フロントエンド生成、**エラーハンドリングとガードレール**。

キーワード: pandas / パレート図 / p 管理図(SPC, UCL/LCL)/ FPY / 4M 分析 / Recharts / バイブ・アナリティクス。

---

## 2. 到達点(この回が終わると何が動くか)

- **統計 API `GET /api/dashboard/statistics`** が KPI・月次トレンド・現象別パレート・機械別/担当者別/工程別/顧客別・4M別・重大度別を返す(`../../docs/04` §4)。
- **p 管理図 API `GET /api/dashboard/control-chart`** が UCL/LCL 付きの管理図データを返す。
- **KPI ダッシュボード画面(`/dashboard`)** と **データ分析画面(機械別/担当者別/顧客別/時系列)** が Recharts で可視化される。
- **4M 分析 `POST /api/analysis/4m/{defect_id}`** が Claude で分類・要因・改善提案を返し、報告書に保存する。
- **予兆アラート `GET /api/analysis/alerts`** がルールベースで算出され、`/alerts` 画面に表示される。

---

## 3. ハンズオン手順

### 3-1. この回で使う Claude Code / 概念

- **バイブ・アナリティクス**: 「このデータでパレート図を作って」のように自然言語で pandas の集計・可視化コードを生成させる。
- **Claude Design / Figma 連携(MCP)**: ダッシュボードの見た目を高品質に仕上げる(発展、`../../docs/07`)。
- **ガードレール**: データ 0 件・欠損・n=0 の月など、異常系を「エラーにせず縮退表示」する方針(`../../docs/02` F5)。

**KPI とグラフの定義(押さえておく)**:

| 指標 | 定義 |
|---|---|
| 不良率 | 総不良数 / 総加工数 |
| 直行率 FPY | 1 − 不良率(概算) |
| パレート図 | 現象別件数の降順 + 累積比率(上位3現象で約6割になる想定) |
| p 管理図 | 期間ごとの不良率 p、中心線 p̄、UCL/LCL = p̄ ± 3√(p̄(1−p̄)/n)、LCL は 0 でクリップ |

### 3-2. バイブコーディング プロンプト例

`../../docs/04` §4/§5、`../../docs/06` (c) と整合させます。

**プロンプト例1(EDA からダッシュボード集計へ)**
```
data/defect_reports.csv を pandas で集計して。現象別パレート(件数・比率・累積比率)、
機械別/担当者別/工程別/顧客別の件数・不良率・損失合計、月次トレンド(件数・不良数・
加工数・不良率)、4M別・重大度別の内訳を作って。まずは Notebook で結果を確認したい。
```

**プロンプト例2(統計 API)**
```
GET /api/dashboard/statistics を docs/04 §4 のレスポンス構造そのままに実装して。
date_from/date_to で期間フィルタ。kpi は total_reports, total_defects, total_production,
defect_rate, fpy, total_cost, recurrence_rate, open_count。monthly_trend, pareto_phenomenon
(name/count/ratio/cumulative_ratio), by_machine/by_operator/by_process/by_customer, by_4m,
by_severity も返す。集計は SQL か pandas、どちらでも可だが件数と一致すること。
```

**プロンプト例3(p 管理図)**
```
GET /api/dashboard/control-chart?months=12 を実装して。docs/04 §4 のとおり
各期間(月)で n(加工数)・defects・p(不良率)・UCL・LCL を返す。
UCL/LCL = p̄ ± 3*sqrt(p̄(1−p̄)/n)、LCL は 0 で下限クリップ。p_bar も返す。
n=0 の月は計算から除外して。
```

**プロンプト例4(ダッシュボード画面 — Recharts)**
```
/dashboard を作って。上部に期間フィルタと KPI カード6枚(件数/不良率/直行率/総損失/
再発率/未対応)。月次トレンドは LineChart、現象別パレートは ComposedChart(棒=件数 +
線=累積比率)、重大度別・4M別は内訳、p 管理図は LineChart + ReferenceLine で UCL/LCL/p̄。
配色は docs/05 §5 のテーマ(CNCコックピット、`app/frontend/src/theme.ts` の palette)に合わせて。データ0件は
「データがありません」を表示(エラーにしない)。
```

**プロンプト例5(4M 分析)**
```
POST /api/analysis/4m/{defect_id} を docs/06 (c) のとおり実装して。
対象報告書を Claude に渡し、output_config の json_schema で
{category_4m(enum Man/Machine/Material/Method), factor(enum), reasoning, improvements[]}
を得る。結果を report の category_4m / factor / ai_improvement に保存。max_tokens 2048。
報告書詳細画面に「4M分析」ボタンと結果カード(分類・要因・理由・改善案)を追加して。
```

**プロンプト例6(予兆アラート)**
```
GET /api/analysis/alerts をルールベースで実装して(docs/04 §5)。
ルール: ①直近30日の不良率が全期間平均の1.5倍超の機械 ②同一現象×同一機械が直近60日に
3件以上 ③直近30日に再発フラグ発生。返すのは
{items:[{level: critical|warning|info, title, message, related:{machine?,phenomenon?}}]}。
/alerts 画面にレベル順で表示して。
```

---

## 4. 動作確認方法

**統計**:
```bash
curl -s "http://localhost:8000/api/dashboard/statistics?date_from=2025-04-01&date_to=2026-03-31" | python -m json.tool
# kpi.total_reports が 100、pareto_phenomenon の上位3件の cumulative_ratio が ~0.6 付近
```

**p 管理図**:
```bash
curl -s "http://localhost:8000/api/dashboard/control-chart?months=12" | python -m json.tool
# items に period/n/defects/p/ucl/lcl、p_bar が入る。lcl が負にならない(0クリップ)
```

**4M 分析**(既存の報告書 ID を指定):
```bash
curl -X POST http://localhost:8000/api/analysis/4m/KZ25-0001
# {"category_4m":"Machine","factor":"工具摩耗","reasoning":"...","improvements":[...]}
```

**アラート**:
```bash
curl -s http://localhost:8000/api/analysis/alerts | python -m json.tool
```

**フロント**: `/dashboard` で KPI カードと各グラフが描画され、期間変更で更新されること。パレートの累積線が右肩上がりで 100% に達すること。`/alerts` にアラートが並ぶこと。報告書詳細で「4M分析」を実行して結果が保存されること。

---

## 5. つまずきポイントと対処

| 症状 | 原因 | 対処 |
|---|---|---|
| KPI の件数が一覧と合わない | 期間フィルタや重複集計のミス | SQL/pandas の集計を1本化。`total_reports` を一覧の total と突き合わせる。 |
| パレートの累積比率が 100% にならない | 比率の分母違い/丸め | 累積は件数の総和を分母に。最終値が 1.0 になるか検算。 |
| p 管理図の LCL が負 | クリップ忘れ | `max(0, p̄ − 3√...)`(docs/04 §4)。 |
| n=0 の月で ZeroDivision | 加工数 0 の期間 | その月は UCL/LCL 計算から除外(docs/02 F5)。 |
| グラフが真っ黒/見えない | ダークテーマで軸・文字色未設定 | Recharts の軸・グリッド・凡例色をテーマに合わせる(docs/05 §5)。 |
| 4M 分析が enum 外の値を返す | 構造化出力未使用 | json_schema の enum を効かせる(docs/06 (c))。 |
| 4M ボタンが 503 | APIキー未設定 | AI 機能はキー必須。ボタンを無効化し理由表示。 |
| アラートが常に空 | 期間が浅い/しきい値が厳しい | 模擬データは1年分。ルールのしきい値と対象期間を確認。 |
| ダッシュボードが重い | 毎描画で全集計 | 集計 API を1回叩いて使い回す。必要なら期間を絞る。 |
