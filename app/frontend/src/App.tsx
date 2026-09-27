import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import UiControlBridge from './components/UiControlBridge'

// ページはルート単位で遅延読み込みし、初期バンドルを小さく保つ
// (Recharts を使う分析系ページを別チャンクに分離)。Suspense 境界は Layout 側。
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Alerts = lazy(() => import('./pages/Alerts'))
const Reports = lazy(() => import('./pages/Reports'))
const ReportDetail = lazy(() => import('./pages/ReportDetail'))
const ReportNew = lazy(() => import('./pages/ReportNew'))
const AnalysisBreakdown = lazy(() => import('./pages/AnalysisBreakdown'))
const AnalysisTrends = lazy(() => import('./pages/AnalysisTrends'))
const Chat = lazy(() => import('./pages/Chat'))
const Masters = lazy(() => import('./pages/Masters'))
const Digests = lazy(() => import('./pages/Digests'))
const Capa = lazy(() => import('./pages/Capa'))
const GraphMap = lazy(() => import('./pages/GraphMap'))
const Ontology = lazy(() => import('./pages/Ontology'))

export default function App() {
  return (
    <>
    <UiControlBridge />
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/digests" element={<Digests />} />
        <Route path="/capa" element={<Capa />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/reports/new" element={<ReportNew />} />
        <Route path="/reports/:defectId" element={<ReportDetail />} />
        <Route path="/analysis/machines" element={<AnalysisBreakdown kind="machine" />} />
        <Route path="/analysis/operators" element={<AnalysisBreakdown kind="operator" />} />
        <Route path="/analysis/customers" element={<AnalysisBreakdown kind="customer" />} />
        <Route path="/analysis/trends" element={<AnalysisTrends />} />
        <Route path="/analysis/graph" element={<GraphMap />} />
        <Route path="/analysis/ontology" element={<Ontology />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/settings/masters" element={<Masters />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
    </>
  )
}
