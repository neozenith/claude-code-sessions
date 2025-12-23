import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import DailyUsage from './pages/DailyUsage'
import WeeklyUsage from './pages/WeeklyUsage'
import MonthlyUsage from './pages/MonthlyUsage'
import HourlyUsage from './pages/HourlyUsage'
import HourOfDay from './pages/HourOfDay'
import Projects from './pages/Projects'
import DrillDown from './pages/DrillDown'

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
        <Route path="/drilldown" element={<DrillDown />} />
      </Routes>
    </Layout>
  )
}
