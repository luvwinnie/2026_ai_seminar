import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ReportDetailPage from './pages/ReportDetailPage'
import ReportListPage from './pages/ReportListPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/reports" element={<ReportListPage />} />
        <Route path="/reports/:defectId" element={<ReportDetailPage />} />
        {/* / と、どれにも当たらないパスは一覧へ送る */}
        <Route path="*" element={<Navigate to="/reports" replace />} />
      </Route>
    </Routes>
  )
}
