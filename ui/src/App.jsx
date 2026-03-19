import { Routes, Route, NavLink } from 'react-router-dom'
import GeneratePulse from './pages/GeneratePulse'
import History from './pages/History'
import './App.css'

export default function App() {
  return (
    <div className="app">
      <nav className="navbar">
        <span className="navbar-brand">🌱 GROWW Weekly Pulse</span>
        <div className="navbar-links">
          <NavLink to="/" end className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            New Pulse
          </NavLink>
          <NavLink to="/history" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            History
          </NavLink>
        </div>
      </nav>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<GeneratePulse />} />
          <Route path="/history" element={<History />} />
        </Routes>
      </main>
    </div>
  )
}
