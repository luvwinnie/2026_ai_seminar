import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'

// 第4回「Claude API」: 一覧・詳細に加えて チャット を追加。
// 新規作成 / ダッシュボード / 分析 は後の回で追加する。
const Reports = lazy(() => import('./pages/Reports'))
const ReportDetail = lazy(() => import('./pages/ReportDetail'))
const Chat = lazy(() => import('./pages/Chat'))

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/reports" replace />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/reports/:defectId" element={<ReportDetail />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="*" element={<Navigate to="/reports" replace />} />
      </Route>
    </Routes>
  )
}
