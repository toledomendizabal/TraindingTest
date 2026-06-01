import React, { useState, useEffect } from 'react'
import { backtestingApi } from '../services/api'

function BacktestingPage() {
  const [reports, setReports] = useState([])
  const [latestReport, setLatestReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const [reportsRes, latestRes] = await Promise.all([
        backtestingApi.getReports(),
        backtestingApi.getLatestReport('daily')
      ])
      setReports(reportsRes.data.reports || [])
      setLatestReport(latestRes.data.report)
    } catch (err) {
      console.error('Error fetching backtesting data:', err)
    } finally {
      setLoading(false)
    }
  }

  const runBacktest = async (type) => {
    setRunning(true)
    try {
      const response = type === 'daily' 
        ? await backtestingApi.runDaily()
        : await backtestingApi.runWeekly()
      
      alert(`Backtesting ${type} completado. Win Rate: ${response.data.result.win_rate}%`)
      fetchData()
    } catch (err) {
      alert('Error al ejecutar backtesting')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Backtesting</h1>
          <p className="text-sm text-gray-400">Análisis de rendimiento y retroalimentación</p>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => runBacktest('daily')}
            disabled={running}
            className="btn-primary text-sm"
          >
            {running ? 'Ejecutando...' : 'Backtest Diario'}
          </button>
          <button
            onClick={() => runBacktest('weekly')}
            disabled={running}
            className="btn-secondary text-sm"
          >
            Backtest Semanal
          </button>
        </div>
      </div>

      {/* Latest Report */}
      {latestReport && (
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Último Reporte</h2>
          <pre className="bg-dark-400 rounded-lg p-4 text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap font-mono max-h-96 overflow-y-auto scrollbar-thin">
            {latestReport}
          </pre>
        </div>
      )}

      {/* KPI Targets */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="stat-card">
          <p className="text-xs text-gray-400 uppercase">Win Rate Objetivo</p>
          <p className="text-2xl font-bold text-primary-400 mt-1">&gt;75%</p>
          <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
            <div className="bg-primary-500 h-2 rounded-full" style={{ width: '55%' }}></div>
          </div>
        </div>
        <div className="stat-card">
          <p className="text-xs text-gray-400 uppercase">Profit Factor</p>
          <p className="text-2xl font-bold text-green-400 mt-1">&gt;1.5</p>
          <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
            <div className="bg-green-500 h-2 rounded-full" style={{ width: '60%' }}></div>
          </div>
        </div>
        <div className="stat-card">
          <p className="text-xs text-gray-400 uppercase">Max Drawdown</p>
          <p className="text-2xl font-bold text-yellow-400 mt-1">&lt;10%</p>
          <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
            <div className="bg-yellow-500 h-2 rounded-full" style={{ width: '30%' }}></div>
          </div>
        </div>
        <div className="stat-card">
          <p className="text-xs text-gray-400 uppercase">Latencia</p>
          <p className="text-2xl font-bold text-blue-400 mt-1">&lt;2s</p>
          <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
            <div className="bg-blue-500 h-2 rounded-full" style={{ width: '80%' }}></div>
          </div>
        </div>
      </div>

      {/* Reports List */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">Historial de Reportes</h2>
        {reports.length > 0 ? (
          <div className="space-y-2">
            {reports.map((report, idx) => (
              <div key={idx} className="flex items-center justify-between bg-dark-400 rounded-lg px-4 py-3">
                <div className="flex items-center space-x-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    report.type === 'weekly' ? 'bg-purple-500/20 text-purple-400' : 'bg-blue-500/20 text-blue-400'
                  }`}>
                    {report.type === 'weekly' ? 'Semanal' : 'Diario'}
                  </span>
                  <span className="text-sm text-gray-300">{report.filename}</span>
                </div>
                <span className="text-xs text-gray-500">{report.date}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-center text-gray-500 py-4">No hay reportes disponibles</p>
        )}
      </div>
    </div>
  )
}

export default BacktestingPage
