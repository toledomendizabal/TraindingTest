import React, { useState, useEffect } from 'react'
import { RefreshCw, TrendingUp, Zap, Repeat, Timer, HelpCircle } from 'lucide-react'
import { strategiesApi } from '../services/api'

const STRATEGY_ICONS = {
  TREND_MTF: TrendingUp,
  BREAKOUT_VOLUME: Zap,
  REVERSAL_ZONES: Repeat,
  SCALPING_TRIPLE: Timer,
}

const STRATEGY_COLORS = {
  TREND_MTF: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  BREAKOUT_VOLUME: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
  REVERSAL_ZONES: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
  SCALPING_TRIPLE: 'text-orange-400 bg-orange-500/10 border-orange-500/30',
}

const STRATEGY_SHORT_NAMES = {
  TREND_MTF: 'Tendencia MTF',
  BREAKOUT_VOLUME: 'Breakout + Volumen',
  REVERSAL_ZONES: 'Reversión en Zonas',
  SCALPING_TRIPLE: 'Scalping Triple',
}

function StrategyRecommendations() {
  const [recommendations, setRecommendations] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  useEffect(() => {
    fetchRecommendations()
  }, [])

  const fetchRecommendations = async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true)
    try {
      const res = await strategiesApi.getRecommendations()
      setRecommendations(res.data.recommendations || [])
      setLastUpdated(new Date())
      setError(null)
    } catch (err) {
      setError('No se pudieron cargar las recomendaciones de estrategia')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  if (loading) {
    return (
      <div className="card">
        <p className="text-gray-400 text-sm">Diagnosticando régimen de mercado por activo...</p>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Estrategia recomendada por activo</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Según el documento "4 Estrategias de Trading Multi-Timeframe"
            {lastUpdated && ` · actualizado ${lastUpdated.toLocaleTimeString()}`}
          </p>
        </div>
        <button
          onClick={() => fetchRecommendations(true)}
          disabled={refreshing}
          className="p-1.5 rounded-lg bg-dark-300 hover:bg-dark-200 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
        </button>
      </div>

      {error && <p className="text-red-400 text-xs mb-3">{error}</p>}

      <div className="space-y-2">
        {recommendations.map((rec) => {
          const Icon = rec.recommended ? (STRATEGY_ICONS[rec.recommended] || HelpCircle) : HelpCircle
          const colorClass = rec.recommended
            ? STRATEGY_COLORS[rec.recommended]
            : 'text-gray-500 bg-dark-300/40 border-gray-700/30'

          return (
            <div key={rec.asset} className={`border rounded-lg p-3 ${colorClass}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Icon size={16} />
                  <span className="font-medium text-white">{rec.asset}</span>
                </div>
                <span className="text-xs font-medium">
                  {rec.recommended ? STRATEGY_SHORT_NAMES[rec.recommended] : 'Sin condición clara'}
                </span>
              </div>
              <p className="text-xs text-gray-400 mt-1.5">{rec.reason}</p>
              {rec.notes && rec.notes.length > 0 && (
                <ul className="mt-1.5 space-y-0.5">
                  {rec.notes.map((note, i) => (
                    <li key={i} className="text-[11px] text-gray-500">· {note}</li>
                  ))}
                </ul>
              )}
            </div>
          )
        })}
      </div>

      {recommendations.length === 0 && !error && (
        <p className="text-gray-500 text-sm">No hay activos configurados.</p>
      )}
    </div>
  )
}

export default StrategyRecommendations
