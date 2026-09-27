# 第3回 演習ガイド — アプリ設計と土台づくり

> **この回の到達点コードは、このディレクトリの `backend/` `frontend/` にあります**(セミナー各回のスナップショット)。本ガイドは講師・受講者双方が手を動かすための手順書です。

対象アプリ: **DefectReport AI**(製造業の不適合報告書分析 AI)。設計ドキュメントは `../../docs/`、完成形は `../../app/` を参照。

---

## 1. この回の学習目標

セミナー企画書 第3回「アプリ設計と土台づくり」に対応。

- Claude とともに**要件定義・仕様**を読み解き、これから作るものの全体像を掴む。
- **アーキテクチャ設計とプロジェクト雛形**の生成(フロントエンド/バックエンドのスキャフォールド)を Claude Code で行う。
- **Artifacts** による画面プロトタイプ/UI デザインの試作を体験する。
- **Git** によるバージョン管理と Claude Code の併用を身につける。
- 【演習】不良報告データの**データモデル設計**と、簡単な **EDA(探索的データ分析)**。

キーワード: React + TypeScript / Vite / FastAPI / SQLite / SQLAlchemy / pandas / 計画モード / CLAUDE.md。

---

## 2. 到達点(この回が終わると何が動くか)

- フロント(Vite + React + TS)とバック(FastAPI)の**プロジェクト雛形**が起動する。
- `../../docs/03_データモデル設計書.md` に沿った **SQLite テーブル `defect_reports`** と SQLAlchemy モデルが用意される。
- 起動時に模擬データ(`../../data/defect_reports.csv`、100件)を **自動シード**する。
- **一覧 API `GET /api/reports`** と、それを表示する**一覧画面**が動く。
- `GET /health` が `{"status":"ok","reports":<件数>,...}` を返す。
- pandas による**簡単な EDA**(件数分布・現象別集計・機械別集計)を Notebook かスクリプトで実行できる。

> この回では AI 機能(チャット・抽出・分析)はまだ入れません。まず「データが見える土台」を作ります。

---

## 3. ハンズオン手順

### 3-1. Claude Code の準備

この回で新しく使う Claude Code の機能:

- **CLAUDE.md**: プロジェクト直下に置く「常設のプロジェクト・ブリーフ」。技術スタック・コマンド・規約・禁止事項を書き、毎回自動で読み込ませる。まず `/init` で雛形を生成し、`/memory` で追記する。
- **計画モード(Plan Mode / Shift+Tab)**: 実装前に Claude に計画を立てさせ、内容を確認・修正してから実行する。雛形生成のような大きめの作業はまず計画モードで。
- **/model**: 計画は Opus、実装は Sonnet といった使い分け(`opusplan`)。
- **Git 併用**: 各ステップの節目でコミット。エラー時は `git diff` を Claude に見せる。

**CLAUDE.md に最低限書く内容(例)**:

```
# DefectReport AI
製造業の不適合報告書を分析する Web アプリ。
## 技術スタック
- フロント: React 19 + TypeScript + Vite + MUI + Recharts
- バック: FastAPI (Python 3.12) + SQLAlchemy + SQLite
## 規約
- API/DB のフィールド名は docs/03_データモデル設計書.md に一致させる
- API 仕様は docs/04_API設計書.md に従う
## コマンド
- バック: cd app/backend && uvicorn main:app --reload --port 8000
- フロント: cd app/frontend && npm run dev
```

### 3-2. バイブコーディング プロンプト例

「良いプロンプトの5要素(目的/利用者/技術スタック/入出力・データ/制約)」を意識した具体例です。設計は `../../docs/03`・`../../docs/04` と整合させます。

**プロンプト例1(プロジェクト雛形 — 計画モードで)**
```
DefectReport AI の土台を作りたい。目的は製造業の不適合報告書を一覧表示すること。
技術スタックは FastAPI(Python 3.12)+ SQLAlchemy + SQLite のバックエンドと、
React 19 + TypeScript + Vite + MUI のフロントエンド。
まずはディレクトリ構成と、各ファイルの役割だけを計画として提示して。
実装はまだしないで。docs/04_API設計書.md の構成(backend は port 8000、frontend は
5173 で /api と /health を 8000 にプロキシ)に合わせて。
```

**プロンプト例2(データモデルと DB)**
```
docs/03_データモデル設計書.md の §2 のテーブル定義そのままに、SQLAlchemy モデル
DefectReport を app/backend/models.py に作って。カラム名・型・必須・既定値
(status は 'open'、has_procedure は true、is_recurrence は false)を厳守。
defect_rate は保存せず、API レスポンス時に defect_count / production_count で
計算する派生値にすること。
```

**プロンプト例3(CSV 自動シード)**
```
起動時に SQLite が空なら data/defect_reports.csv(100件)を読み込んで
defect_reports テーブルにシードする処理を書いて。CSV のカラム名は API フィールド名と
同一(id, created_at, updated_at, ai_improvement は含まない)。total_cost が空の行は
material/processing/outsourcing/other_cost を合算してサーバ側で埋めて。
```

**プロンプト例4(一覧 API + 画面)**
```
GET /api/reports を docs/04_API設計書.md §2 の仕様どおりに実装して。
クエリ q, status, severity, machine, process, category_4m, date_from, date_to,
limit(既定50・最大500), offset, sort(既定 -occurrence_date)に対応。
レスポンスは {"total": int, "items": [Report]}。
続いてフロントに、この API を叩いて MUI の DataGrid で表示する一覧画面を作って。
列は defect_id / occurrence_date / customer / process / machine_name / phenomenon /
severity / status。行クリックで詳細(まだ空でよい)に遷移。
```

**プロンプト例5(EDA)**
```
data/defect_reports.csv を pandas で読み込んで簡単な EDA をして。
現象(phenomenon)別の件数トップ5、機械(machine_name)別の件数と平均不良率、
月別の件数推移を出して。パレート図が意味を持つか(上位3現象で約6割か)も確認して。
結果は表とコメントで示して。
```

---

## 4. 動作確認方法

**バックエンド**(`app/backend` を起動後):
```bash
# ヘルスチェック(reports 件数が 100 になっていれば自動シード成功)
curl http://localhost:8000/health

# 一覧(先頭5件)
curl "http://localhost:8000/api/reports?limit=5"

# 絞り込み(重大度 high・旋盤工程)
curl "http://localhost:8000/api/reports?severity=high&process=旋盤"
```

**フロントエンド**: ブラウザで http://localhost:5173 を開き、一覧画面に 100 件のデータが表示され、検索・フィルタ・ページングが効くことを確認。

**EDA**: 実行して現象別トップ・機械別集計が出力されること。

---

## 5. つまずきポイントと対処

| 症状 | 原因 | 対処 |
|---|---|---|
| `/health` の reports が 0 | CSV のパス違い、または列名不一致でシード失敗 | CSV の列名を `docs/03` §2 のフィールド名に合わせる。シードのログを Claude に貼って原因を聞く。 |
| 一覧が空/500 エラー | モデルとテーブルの不整合、SQLite ファイル未生成 | `app/backend/data/` の DB を一度削除して再起動。エラーの stack trace をそのまま Claude に貼る。 |
| フロントで CORS/404 | `/api` プロキシ未設定 | `vite.config.ts` の proxy で `/api` `/health` を `http://localhost:8000` へ。docs/04 冒頭の記述に合わせる。 |
| 日付フィルタが効かない | `occurrence_date` が文字列で比較 | DATE 型で保存し、`date_from`/`date_to` は ISO 文字列で比較。 |
| Claude が一気に作りすぎる | 指示が大きすぎる | 「一度に作りすぎない」。計画モードで区切り、①雛形 ②モデル ③シード ④一覧、と小さく依頼する。 |
| defect_rate が null 連発 | production_count が 0 | 0 除算時は null を返す仕様(docs/03 派生値)。画面は「-」表示にする。 |
