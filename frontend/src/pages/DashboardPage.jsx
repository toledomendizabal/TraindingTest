import React, { useState, useEffect } from 'react'
import { dashboardApi, signalsApi } from '../services/api'

function StatCard({ title, value, subtitle, color = 'primary' }) {
  const colorClasses = {
    primary: 'text-primary-400',
    green: 'text-green-400',
    red: 'text-red-400',
    yellow: 'text-yellow-400',
    blue: 'text-blue-400'
  }

  return (
    <div className="stat-card">
      <p className="text-xs text-gray-400 uppercase tracking-wide">{title}</p>
      <p className={`text-2xl font-bold mt-1 ${colorClasses[color]}`}>{value}</p>
      {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
    </div>
  )
}

function DashboardPage() {
  const [overview, setOverview] = useState(null)
  const [kpis, setKpis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000) // Refresh every 5s
    return () => clearInterval(interval)
  }, [])

  const fetchData = async () => {
    try {
      const [overviewRes, kpisRes] = await Promise.all([
        dashboardApi.getOverview(),
        dashboardApi.getKPIs()
      ])
      setOverview(overviewRes.data)
      setKpis(kpisRes.data)
      setError(null)
    } catch (err) {
      setError('Error al cargar datos del dashboard')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-primary-500"></div>
      </div>
    )
  }

  const stats = overview?.statistics || {}
  const activeSignals = overview?.active_signals || []

  return (
    <div className="space-y-6">
      {/* Page Title */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-400">Vista general del sistema de trading</p>
        </div>
        <div className="flex items-center space-x-2">
          <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
          <span className="text-sm text-green-400">En tiempo real</span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard 
          title="Win Rate" 
          value={`${kpis?.win_rate?.value || 0}%`}
          subtitle="Objetivo: 75%"
          color={kpis?.win_rate?.value >= 55 ? 'green' : 'red'}
        />
        <StatCard 
          title="Profit Factor" 
          value={kpis?.profit_factor?.value || '0.00'}
          subtitle="Objetivo: >1.5"
          color={kpis?.profit_factor?.value >= 1.5 ? 'green' : 'yellow'}
        />
        <StatCard 
          title="Señales Activas" 
          value={kpis?.active_signals || 0}
          subtitle={`Total: ${kpis?.total_signals || 0}`}
          color="blue"
        />
        <StatCard 
          title="Ganancia Neta" 
          value={`$${kpis?.net_profit || 0}`}
          subtitle="Capital: $10,000"
          color={kpis?.net_profit >= 0 ? 'green' : 'red'}
        />
        <StatCard 
          title="Drawdown" 
          value={`${kpis?.drawdown?.value || 0}%`}
          subtitle="Máximo: 10%"
          color={kpis?.drawdown?.value <= 10 ? 'green' : 'red'}
        />
      </div>

      {/* Active Signals Table */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Señales Activas</h2>
          <span className="text-xs bg-primary-500/20 text-primary-400 px-2 py-1 rounded">
            {activeSignals.length} activas
          </span>
        </div>

        {activeSignals.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-gray-700/50">
                  <th className="text-left py-2 px-3">Activo</th>
                  <th className="text-left py-2 px-3">Dirección</th>
                  <th className="text-right py-2 px-3">Entrada</th>
                  <th className="text-right py-2 px-3">SL</th>
	                  <th className="text-right py-2 px-3">TP1</th>
	                  <th className="text-right py-2 px-3">Lote</th>
	                  <th className="text-right py-2 px-3">Drawdown</th>
	                  <th className="text-right py-2 px-3">RR</th>
	                  <th className="text-right py-2 px-3">Sesión</th>
                </tr>
              </thead>
              <tbody>
                {activeSignals.map((signal, idx) => (
                  <tr key={idx} className="border-b border-gray-700/30 hover:bg-gray-700/20">
                    <td className="py-2 px-3 font-medium text-white">{signal.asset}</td>
                    <td className="py-2 px-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        signal.direction === 'BUY' 
                          ? 'bg-green-500/20 text-green-400' 
                          : 'bg-red-500/20 text-red-400'
                      }`}>
                        {signal.direction}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right font-mono">{signal.entry_price}</td>
                    <td className="py-2 px-3 text-right font-mono text-red-400">{signal.stop_loss}</td>
	                    <td className="py-2 px-3 text-right font-mono text-green-400">{signal.take_profit_1}</td>
	                    <td className="py-2 px-3 text-right">{signal.lot_size}</td>
	                    <td className="py-2 px-3 text-right font-mono text-orange-400">{signal.max_drawdown || 0}%</td>
	                    <td className="py-2 px-3 text-right font-mono text-blue-400">{signal.risk_reward_ratio || 0}</td>
	                    <td className="py-2 px-3 text-right text-gray-400">{signal.session}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <p className="text-lg mb-2">Sin señales activas</p>
            <p className="text-sm">El sistema está analizando los mercados...</p>
          </div>
        )}
      </div>

      {/* Statistics Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold text-white mb-4">Resumen de Operaciones</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Total Señales</span>
              <span className="text-white font-medium">{stats.total_signals || 0}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Ganadoras</span>
              <span className="text-green-400 font-medium">{stats.wins || 0}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Perdedoras</span>
              <span className="text-red-400 font-medium">{stats.losses || 0}</span>
            </div>
            <div className="border-t border-gray-700/50 pt-3 flex justify-between items-center">
              <span className="text-gray-400">Ganancia Total</span>
              <span className="text-green-400 font-medium">${stats.total_profit || 0}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Pérdida Total</span>
              <span className="text-red-400 font-medium">${stats.total_loss || 0}</span>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold text-white mb-4">Activos Monitoreados</h3>
          <div className="grid grid-cols-3 gap-2">
            {(overview?.active_assets || []).map((asset) => (
              <div key={asset} className="bg-dark-400 rounded-lg px-3 py-2 text-center">
                <span className="text-xs text-gray-300">{asset}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}
    </div>
  )
}

export default DashboardPage
