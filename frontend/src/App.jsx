import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import Overview from './pages/Overview.jsx'
import NodeDetail from './pages/NodeDetail.jsx'
import Ledger from './pages/Ledger.jsx'
import Results from './pages/Results.jsx'
import Method from './pages/Method.jsx'
import { ThemeContext } from './theme.js'

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('theme') || 'system' } catch { return 'system' }
  })
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    try { localStorage.setItem('theme', theme) } catch { /* private mode */ }
  }, [theme])
  const next = { system: 'light', light: 'dark', dark: 'system' }
  const cycle = () => {
    const t = next[theme]
    // Apply before re-render so components that read CSS variables
    // during render (the map) pick up the new colours straight away.
    if (t === 'system') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', t)
    setTheme(t)
  }
  return [theme, cycle]
}

export default function App() {
  const [theme, cycleTheme] = useTheme()
  return (
    <ThemeContext.Provider value={theme}>
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="7" fill="#1c5cab" />
            <path d="M9 22c0-7 5-12 14-12-1 8-5 13-12 13" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
            <circle cx="10" cy="22" r="2" fill="#fff" />
          </svg>
          <div>
            <b>FoodTrace</b>
            <small>forecast reliability</small>
          </div>
        </div>
        <nav className="nav">
          <NavLink to="/" end>Supply map</NavLink>
          <NavLink to="/results">Evaluation</NavLink>
          <NavLink to="/ledger">Provenance ledger</NavLink>
          <NavLink to="/method">Data &amp; method</NavLink>
        </nav>
        <div className="side-foot">
          <button className="theme-btn" onClick={cycleTheme}>Theme: {theme}</button>
          <span>Data: UN Comtrade, openFDA, CDC NORS</span>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/node/:id" element={<NodeDetail />} />
          <Route path="/results" element={<Results />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/method" element={<Method />} />
          <Route path="*" element={<p className="empty">Page not found.</p>} />
        </Routes>
      </main>
    </div>
    </ThemeContext.Provider>
  )
}
