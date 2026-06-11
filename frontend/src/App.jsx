import React, { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import DashboardPage from './pages/DashboardPage'
import SignalsPage from './pages/SignalsPage'
import BacktestingPage from './pages/BacktestingPage'
import ConfigPage from './pages/ConfigPage'
import LogsPage from './pages/LogsPage'
import LoginPage from './pages/LoginPage'
import ChartPage from './pages/ChartPage'
import { api } from './services/api'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  useEffect(() => {
    checkAuth()
  }, [])

  const checkAuth = async () => {
    try {
      const response = await api.get('/auth/status')
      setIsAuthenticated(response.data.authenticated)
      setUser(response.data.user)
    } catch (error) {
      console.error('Auth check failed:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleLogin = async () => {
    try {
      const response = await api.post('/auth/login')
      if (response.data.auth_url) {
        window.location.href = response.data.auth_url
      }
    } catch (error) {
      console.error('Login failed:', error)
    }
  }

  const handleLogout = async () => {
    try {
      await api.post('/auth/logout')
      setIsAuthenticated(false)
      setUser(null)
    } catch (error) {
      console.error('Logout failed:', error)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-dark-500">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary-500 mx-auto mb-4"></div>
          <p className="text-gray-400">Cargando TradingSignal Pro...</p>
        </div>
      </div>
    )
  }

  return (
    <Router>
      <div className="flex h-screen bg-dark-500">
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />
        
        <div className="flex-1 flex flex-col overflow-hidden">
          <Header 
            user={user} 
            isAuthenticated={isAuthenticated}
            onLogin={handleLogin}
            onLogout={handleLogout}
          />
          
          <main className="flex-1 overflow-y-auto p-6 scrollbar-thin">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/signals" element={<SignalsPage />} />
              <Route path="/backtesting" element={<BacktestingPage />} />
              <Route path="/config" element={<ConfigPage />} />
              <Route path="/logs" element={<LogsPage />} />
              <Route path="/charts" element={<ChartPage />} />
              <Route path="/login" element={<LoginPage onLogin={handleLogin} />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </Router>
  )
}

export default App
