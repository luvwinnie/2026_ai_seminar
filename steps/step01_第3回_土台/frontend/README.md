# DefectReport AI — フロントエンド

製造業 不良報告分析AI(セミナー完成イメージアプリ)の SPA。Vite + React + TypeScript + MUI + Recharts + React Router + axios。

## 開発

```bash
npm install
npm run dev      # http://localhost:5173 (/api・/health を localhost:8000 へプロキシ)
npm run build    # 型チェック + 本番ビルド (dist/)
npm run lint     # oxlint
```

バックエンド(FastAPI, ポート8000)を別途起動しておくと API が疎通する。

## 画面構成

- 経営者向け: サマリー(`/dashboard`)、予測アラート(`/alerts`)
- 不適合報告書: 一覧・検索(`/reports`)、新規作成(`/reports/new`)、詳細(`/reports/:defectId`)
- データ分析: 機械別 / 担当者別 / 顧客別(`/analysis/*`)、時系列(`/analysis/trends`)
- AI: チャット(`/chat`、SSE ストリーミング + RAG 参照元表示)

## ディレクトリ

- `src/api/` — axios クライアント、エンドポイント、チャット SSE パーサ
- `src/components/` — レイアウト(サイドバー)、共通 UI、報告書フォーム
- `src/pages/` — 各画面
- `src/types.ts` — API レスポンス型(`docs/04_API設計書.md` 準拠)
- `src/constants/vocab.ts` — 工程・機械・現象などの語彙(`docs/03` 準拠)

## Docker

`Dockerfile`(node ビルド → nginx 配信)+ `nginx.conf`(`/api`・`/health` を `backend:8000` へプロキシ、SSE 対応)。
