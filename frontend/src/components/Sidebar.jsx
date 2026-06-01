import React from 'react'
import { NavLink } from 'react-router-dom'

const menuItems = [
  { path: '/', label: 'Dashboard', icon: '📊' },
  { path: '/signals', label: 'Señales', icon: '📈' },
  { path: '/backtesting', label: 'Backtesting', icon: '🔄' },
  { path: '/config', label: 'Configuración', icon: '⚙️' },
  { path: '/logs', label: 'Logs', icon: '📋' },
]

function Sidebar({ isOpen, onToggle }) {
  return (
    <aside className={`${isOpen ? 'w-64' : 'w-16'} bg-dark-200 border-r border-gray-700/50 transition-all duration-300 flex flex-col`}>
      {/* Logo */}
      <div className="p-4 border-b border-gray-700/50">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 bg-primary-500 rounded-lg flex items-center justify-center font-bold text-sm">
            TS
          </div>
          {isOpen && (
            <div>
              <h1 className="text-sm font-bold text-white">TradingSignal</h1>
              <p className="text-xs text-primary-400">Pro v1.0</p>
            </div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1">
        {menuItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `flex items-center space-x-3 px-3 py-2.5 rounded-lg transition-colors ${
                isActive
                  ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                  : 'text-gray-400 hover:bg-gray-700/50 hover:text-white'
              }`
            }
          >
            <span className="text-lg">{item.icon}</span>
            {isOpen && <span className="text-sm font-medium">{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Toggle button */}
      <div className="p-3 border-t border-gray-700/50">
        <button
          onClick={onToggle}
          className="w-full flex items-center justify-center py-2 text-gray-400 hover:text-white transition-colors"
        >
          {isOpen ? '◀' : '▶'}
        </button>
      </div>
    </aside>
  )
}

export default Sidebar
