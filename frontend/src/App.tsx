import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import DailyUsage from './pages/DailyUsage'
import WeeklyUsage from './pages/WeeklyUsage'
import MonthlyUsage from './pages/MonthlyUsage'
import HourlyUsage from './pages/HourlyUsage'
import HourOfDay from './pages/HourOfDay'
import Projects from './pages/Projects'
import SessionsList from './pages/SessionsList'
import ProjectSessions from './pages/ProjectSessions'
import SessionDetail from './pages/SessionDetail'
import Timeline from './pages/Timeline'
import SchemaTimeline from './pages/SchemaTimeline'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/daily" element={<DailyUsage />} />
        <Route path="/weekly" element={<WeeklyUsage />} />
        <Route path="/monthly" element={<MonthlyUsage />} />
        <Route path="/hourly" element={<HourlyUsage />} />
        <Route path="/hour-of-day" element={<HourOfDay />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/sessions" element={<SessionsList />} />
        <Route path="/sessions/:projectId" element={<ProjectSessions />} />
        <Route path="/sessions/:projectId/:sessionId" element={<SessionDetail />} />
        <Route path="/timeline" element={<Timeline />} />
        <Route path="/schema-timeline" element={<SchemaTimeline />} />
      </Routes>
    </Layout>
  )
}
