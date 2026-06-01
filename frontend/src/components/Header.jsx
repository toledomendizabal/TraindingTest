import React, { useState, useEffect } from 'react'

function Header({ user, isAuthenticated, onLogin, onLogout }) {
  const [currentTime, setCurrentTime] = useState(new Date())
  const [session, setSession] = useState('')

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date())
      updateSession()
    }, 1000)
    updateSession()
    return () => clearInterval(timer)
  }, [])

  const updateSession = () => {
    const hour = new Date().getUTCHours()
    if (hour >= 0 && hour < 8) setSession('Tokyo 🇯🇵')
    else if (hour >= 8 && hour < 13) setSession('London 🇬🇧')
    else if (hour >= 13 && hour < 22) setSession('New York 🇺🇸')
    else setSession('Tokyo 🇯🇵')
  }

  return (
    <header className="bg-dark-200 border-b border-gray-700/50 px-6 py-3">
      <div className="flex items-center justify-between">
        {/* Left: Session info */}
        <div className="flex items-center space-x-6">
          <div className="flex items-center space-x-2">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
            <span className="text-sm text-gray-400">Sistema Activo</span>
          </div>
          <div className="text-sm text-gray-300">
            <span className="text-primary-400 font-medium">Sesión:</span> {session}
          </div>
          <div className="text-sm text-gray-400">
            {currentTime.toLocaleTimeString('es-MX', { hour12: false })}
          </div>
        </div>

        {/* Right: Auth */}
        <div className="flex items-center space-x-4">
          {isAuthenticated ? (
            <div className="flex items-center space-x-3">
              <div className="text-right">
                <p className="text-sm text-white">{user?.name || 'Usuario'}</p>
                <p className="text-xs text-gray-400">{user?.email || ''}</p>
              </div>
              <button
                onClick={onLogout}
                className="text-sm text-gray-400 hover:text-red-400 transition-colors"
              >
                Salir
              </button>
            </div>
          ) : (
            <button
              onClick={onLogin}
              className="flex items-center space-x-2 bg-white/10 hover:bg-white/20 text-white px-4 py-2 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              <span className="text-sm">Login con Google</span>
            </button>
          )}
        </div>
      </div>
    </header>
  )
}

export default Header
