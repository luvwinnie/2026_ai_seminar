import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'

// 第3回「土台」: この回にあるのは 一覧 と 詳細(簡易表示)のみ。
// チャット / 新規作成 / ダッシュボード / 分析 は後の回で追加する。
const Reports = lazy(() => import('./pages/Reports'))
const ReportDetail = lazy(() => import('./pages/ReportDetail'))

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/reports" replace />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/reports/:defectId" element={<ReportDetail />} />
        <Route path="*" element={<Navigate to="/reports" replace />} />
      </Route>
    </Routes>
  )
}
