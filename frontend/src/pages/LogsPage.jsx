import React, { useState, useEffect } from 'react'
import { dashboardApi } from '../services/api'

function LogsPage() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lines, setLines] = useState(100)

  useEffect(() => {
    fetchLogs()
    let interval
    if (autoRefresh) {
      interval = setInterval(fetchLogs, 5000)
    }
    return () => clearInterval(interval)
  }, [autoRefresh, lines])

  const fetchLogs = async () => {
    try {
      const response = await dashboardApi.getLogs(lines)
      setLogs(response.data.logs || [])
    } catch (err) {
      console.error('Error fetching logs:', err)
    } finally {
      setLoading(false)
    }
  }

  const getLogLevel = (line) => {
    if (line.includes('ERROR')) return 'text-red-400'
    if (line.includes('WARNING')) return 'text-yellow-400'
    if (line.includes('INFO')) return 'text-green-400'
    if (line.includes('DEBUG')) return 'text-gray-500'
    return 'text-gray-300'
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Logs del Sistema</h1>
          <p className="text-sm text-gray-400">Registro de actividad en tiempo real</p>
        </div>
        <div className="flex items-center space-x-4">
          <select
            value={lines}
            onChange={(e) => setLines(parseInt(e.target.value))}
            className="bg-dark-400 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
          >
            <option value={50}>50 líneas</option>
            <option value={100}>100 líneas</option>
            <option value={200}>200 líneas</option>
            <option value={500}>500 líneas</option>
          </select>
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              autoRefresh
                ? 'bg-green-500/20 text-green-400 border border-green-500/50'
                : 'bg-gray-700 text-gray-400'
            }`}
          >
            {autoRefresh ? '⏸ Auto-refresh ON' : '▶ Auto-refresh OFF'}
          </button>
          <button onClick={fetchLogs} className="btn-secondary text-sm">
            Refrescar
          </button>
        </div>
      </div>

      <div className="card">
        <div className="bg-dark-500 rounded-lg p-4 max-h-[600px] overflow-y-auto scrollbar-thin font-mono text-xs">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-primary-500"></div>
            </div>
          ) : logs.length > 0 ? (
            logs.map((line, idx) => (
              <div key={idx} className={`py-0.5 ${getLogLevel(line)}`}>
                {line}
              </div>
            ))
          ) : (
            <p className="text-gray-500 text-center py-4">No hay logs disponibles</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default LogsPage
