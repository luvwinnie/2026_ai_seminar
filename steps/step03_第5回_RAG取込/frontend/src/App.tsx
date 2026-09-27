import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'

// 第5回「RAG・取り込み」: 新規作成(ファイルアップロード)を追加。
// ダッシュボード / 分析 は第6回で追加する。
const Reports = lazy(() => import('./pages/Reports'))
const ReportDetail = lazy(() => import('./pages/ReportDetail'))
const ReportNew = lazy(() => import('./pages/ReportNew'))
const Chat = lazy(() => import('./pages/Chat'))

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/reports" replace />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/reports/new" element={<ReportNew />} />
        <Route path="/reports/:defectId" element={<ReportDetail />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="*" element={<Navigate to="/reports" replace />} />
      </Route>
    </Routes>
  )
}
