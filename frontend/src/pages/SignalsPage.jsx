import React, { useState, useEffect, useMemo } from 'react'
import { signalsApi } from '../services/api'

const STRATEGY_LABELS = {
  TREND_MTF: 'Tendencia MTF',
  BREAKOUT_VOLUME: 'Breakout + Volumen',
  REVERSAL_ZONES: 'Reversión en Zonas',
  SCALPING_TRIPLE: 'Scalping Triple',
  GENERIC_MULTI_INDICATOR: 'Motor Genérico (18 ind.)',
  UNKNOWN: 'Sin estrategia',
}

const STRATEGY_BADGE_COLORS = {
  TREND_MTF: 'bg-blue-500/20 text-blue-400',
  BREAKOUT_VOLUME: 'bg-yellow-500/20 text-yellow-400',
  REVERSAL_ZONES: 'bg-purple-500/20 text-purple-400',
  SCALPING_TRIPLE: 'bg-orange-500/20 text-orange-400',
  GENERIC_MULTI_INDICATOR: 'bg-gray-500/20 text-gray-300',
  UNKNOWN: 'bg-red-500/20 text-red-400',
}

function SignalsPage() {
  const [signals, setSignals] = useState([])
  const [filter, setFilter] = useState('all') // all, active, closed
  const [strategyFilter, setStrategyFilter] = useState('all') // all, TREND_MTF, BREAKOUT_VOLUME, ...
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)

  useEffect(() => {
    fetchSignals()
    const interval = setInterval(fetchSignals, 10000)
    return () => clearInterval(interval)
  }, [filter])

  const fetchSignals = async () => {
    try {
      let response
      if (filter === 'active') {
        response = await signalsApi.getActive()
      } else if (filter === 'closed') {
        response = await signalsApi.getClosed()
      } else {
        response = await signalsApi.getAll()
      }
      setSignals(response.data || [])
    } catch (err) {
      console.error('Error fetching signals:', err)
    } finally {
      setLoading(false)
    }
  }

  const triggerAnalysis = async () => {
    setAnalyzing(true)
    try {
      const response = await signalsApi.triggerAnalysis()
      alert(`Análisis completado: ${response.data.signals_generated} señales generadas`)
      fetchSignals()
    } catch (err) {
      alert('Error al ejecutar análisis')
    } finally {
      setAnalyzing(false)
    }
  }

  // Estrategias realmente presentes en los datos cargados (para no mostrar
  // botones de filtro de estrategias que nunca aparecieron todavía)
  const availableStrategies = useMemo(() => {
    const set = new Set(signals.map((s) => s.strategy || 'UNKNOWN'))
    return Array.from(set)
  }, [signals])

  const filteredSignals = useMemo(() => {
    if (strategyFilter === 'all') return signals
    return signals.filter((s) => (s.strategy || 'UNKNOWN') === strategyFilter)
  }, [signals, strategyFilter])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Señales de Trading</h1>
          <p className="text-sm text-gray-400">Historial y gestión de señales</p>
        </div>
        <button
          onClick={triggerAnalysis}
          disabled={analyzing}
          className="btn-primary flex items-center space-x-2"
        >
          {analyzing ? (
            <>
              <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white"></div>
              <span>Analizando...</span>
            </>
          ) : (
            <>
              <span>🔍</span>
              <span>Analizar Mercados</span>
            </>
          )}
        </button>
      </div>

      {/* Filters */}
      <div className="flex space-x-2">
        {[
          { key: 'all', label: 'Todas' },
          { key: 'active', label: 'Activas' },
          { key: 'closed', label: 'Cerradas' }
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              filter === key
                ? 'bg-primary-500 text-white'
                : 'bg-gray-700/50 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Filtro por estrategia */}
      {availableStrategies.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setStrategyFilter('all')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              strategyFilter === 'all'
                ? 'bg-primary-500/80 text-white'
                : 'bg-gray-800/50 text-gray-400 hover:bg-gray-700'
            }`}
          >
            Todas las estrategias
          </button>
          {availableStrategies.map((strategyKey) => (
            <button
              key={strategyKey}
              onClick={() => setStrategyFilter(strategyKey)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                strategyFilter === strategyKey
                  ? 'bg-primary-500/80 text-white'
                  : `${STRATEGY_BADGE_COLORS[strategyKey] || 'bg-gray-800/50 text-gray-400'} hover:opacity-80`
              }`}
            >
              {STRATEGY_LABELS[strategyKey] || strategyKey}
            </button>
          ))}
        </div>
      )}

      {/* Signals Table */}
      <div className="card overflow-x-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-primary-500"></div>
          </div>
        ) : filteredSignals.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700/50">
                <th className="text-left py-3 px-3">ID</th>
                <th className="text-left py-3 px-3">Activo</th>
                <th className="text-left py-3 px-3">Estrategia</th>
                <th className="text-left py-3 px-3">Dir.</th>
                <th className="text-right py-3 px-3">Entrada</th>
                <th className="text-right py-3 px-3">SL</th>
                <th className="text-right py-3 px-3">TP1 (1:3)</th>
                <th className="text-right py-3 px-3">TP2 (1:6)</th>
                <th className="text-right py-3 px-3">TP3 (1:10)</th>
                <th className="text-right py-3 px-3">Lote</th>
                <th className="text-right py-3 px-3">Ind.</th>
                <th className="text-right py-3 px-3">SMC Qual.</th>
                <th className="text-right py-3 px-3">RR</th>
                <th className="text-right py-3 px-3">Drawdown</th>
                <th className="text-right py-3 px-3">Duración</th>
                <th className="text-center py-3 px-3">Estado</th>
                <th className="text-right py-3 px-3">P/L</th>
              </tr>
            </thead>
            <tbody>
              {filteredSignals.map((signal, idx) => (
                <tr key={idx} className="border-b border-gray-700/30 hover:bg-gray-700/20">
                  <td className="py-2 px-3 text-gray-500 font-mono text-xs">{signal.id}</td>
                  <td className="py-2 px-3 font-medium text-white">{signal.asset}</td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap ${
                      STRATEGY_BADGE_COLORS[signal.strategy || 'UNKNOWN'] || 'bg-gray-500/20 text-gray-300'
                    }`}>
                      {STRATEGY_LABELS[signal.strategy || 'UNKNOWN'] || signal.strategy || 'Sin estrategia'}
                    </span>
                  </td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${
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
                  <td className="py-2 px-3 text-right font-mono text-green-400">{signal.take_profit_2}</td>
                  <td className="py-2 px-3 text-right font-mono text-green-400">{signal.take_profit_3}</td>
                  <td className="py-2 px-3 text-right">{signal.lot_size}</td>
                  <td className="py-2 px-3 text-right text-primary-400">{signal.indicators_met}/18</td>
                  <td className="py-2 px-3 text-right">
                    <div className="flex flex-col items-end">
                      <span className="font-bold text-yellow-500">{signal.smc_quality || '1.0'}x</span>
                      <div className="flex space-x-1 mt-0.5">
                        {signal.fvg_confluence && <span title="FVG Confluence" className="w-2 h-2 rounded-full bg-blue-500"></span>}
                        {signal.liquidity_sweep && <span title="Liquidity Sweep" className="w-2 h-2 rounded-full bg-purple-500"></span>}
                      </div>
                    </div>
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-blue-400">{signal.risk_reward ? `1:${signal.risk_reward}` : '-'}</td>
                  <td className="py-2 px-3 text-right font-mono text-orange-400">{signal.max_drawdown ? `${signal.max_drawdown}%` : '-'}</td>
                  <td className="py-2 px-3 text-right font-mono text-gray-300">{signal.duration ? `${signal.duration}m` : '-'}</td>
                  <td className="py-2 px-3 text-center">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      signal.status === 'ACTIVE' ? 'bg-blue-500/20 text-blue-400' :
                      signal.status?.includes('TP') ? 'bg-green-500/20 text-green-400' :
                      'bg-red-500/20 text-red-400'
                    }`}>
                      {signal.status}
                    </span>
                  </td>
                  <td className={`py-2 px-3 text-right font-medium ${
                    signal.profit_loss > 0 ? 'text-green-400' :
                    signal.profit_loss < 0 ? 'text-red-400' : 'text-gray-400'
                  }`}>
                    {signal.profit_loss ? `$${signal.profit_loss}` : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-center py-8 text-gray-500">
            {signals.length > 0 && strategyFilter !== 'all' ? (
              <>
                <p className="text-lg mb-2">Ninguna señal coincide con esta estrategia</p>
                <p className="text-sm">Prueba con "Todas las estrategias"</p>
              </>
            ) : (
              <>
                <p className="text-lg mb-2">Sin señales registradas</p>
                <p className="text-sm">Haz clic en "Analizar Mercados" para generar señales</p>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default SignalsPage
