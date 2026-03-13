import { Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import Dashboard from './pages/Dashboard'
import CampaignBuilder from './pages/CampaignBuilder'
import TrendReports from './pages/TrendReports'
import BrandHealth from './pages/BrandHealth'
import EngagementConsole from './pages/EngagementConsole'
import MentorPortal from './pages/MentorPortal'
import DebateRoom from './pages/DebateRoom'

export default function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="campaigns/new" element={<CampaignBuilder />} />
        <Route path="campaigns/:id/debate" element={<DebateRoom />} />
        <Route path="trends" element={<TrendReports />} />
        <Route path="brand-health" element={<BrandHealth />} />
        <Route path="engagement" element={<EngagementConsole />} />
        <Route path="mentor" element={<MentorPortal />} />
      </Route>
    </Routes>
  )
}
