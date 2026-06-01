import React, { useState, useEffect } from 'react'
import { configApi } from '../services/api'

function ConfigPage() {
  const [config, setConfig] = useState(null)
  const [availableAssets, setAvailableAssets] = useState(null)
  const [capital, setCapital] = useState(10000)
  const [riskPct, setRiskPct] = useState(0.3)
  const [minIndicators, setMinIndicators] = useState(6)
  const [tradingMode, setTradingMode] = useState('offline')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchConfig()
  }, [])

  const fetchConfig = async () => {
    try {
      const [configRes, assetsRes, modeRes] = await Promise.all([
        configApi.getCurrent(),
        configApi.getAvailableAssets(),
        configApi.getTradingMode()
      ])
      setConfig(configRes.data)
      setAvailableAssets(assetsRes.data)
      setTradingMode(modeRes.data.mode)

      // Set form values
      const params = configRes.data.parameters || {}
      setCapital(params.initial_capital || 10000)
      setRiskPct(params.risk_percentage || 0.3)
      setMinIndicators(params.min_indicators || 6)
    } catch (err) {
      console.error('Error fetching config:', err)
    } finally {
      setLoading(false)
    }
  }

  const saveParameters = async () => {
    setSaving(true)
    try {
      await configApi.update({
        parameters: {
          initial_capital: parseFloat(capital),
          risk_percentage: parseFloat(riskPct),
          min_indicators: parseInt(minIndicators),
          signal_timeframe: '5m'
        }
      })
      alert('Configuración guardada exitosamente')
    } catch (err) {
      alert('Error al guardar configuración')
    } finally {
      setSaving(false)
    }
  }

  const toggleAsset = async (symbol, currentActive) => {
    try {
      await configApi.toggleAsset(symbol, !currentActive)
      fetchConfig()
    } catch (err) {
      alert('Error al cambiar estado del activo')
    }
  }

  const changeTradingMode = async (mode) => {
    try {
      await configApi.setTradingMode(mode)
      setTradingMode(mode)
    } catch (err) {
      alert('Error al cambiar modo de trading')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-primary-500"></div>
      </div>
    )
  }

  const riskAmount = (capital * riskPct / 100).toFixed(2)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Configuración</h1>
        <p className="text-sm text-gray-400">Ajustes del sistema de trading</p>
      </div>

      {/* Trading Mode */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">Modo de Trading</h2>
        <div className="flex space-x-4">
          <button
            onClick={() => changeTradingMode('offline')}
            className={`flex-1 p-4 rounded-lg border transition-colors ${
              tradingMode === 'offline'
                ? 'border-primary-500 bg-primary-500/10'
                : 'border-gray-700 hover:border-gray-600'
            }`}
          >
            <h3 className="font-medium text-white">Offline (Excel)</h3>
            <p className="text-xs text-gray-400 mt-1">Monitoreo basado en Excel sin conexión a broker</p>
          </button>
          <button
            onClick={() => changeTradingMode('online')}
            className={`flex-1 p-4 rounded-lg border transition-colors ${
              tradingMode === 'online'
                ? 'border-primary-500 bg-primary-500/10'
                : 'border-gray-700 hover:border-gray-600'
            }`}
          >
            <h3 className="font-medium text-white">Online (MetaTrader)</h3>
            <p className="text-xs text-gray-400 mt-1">Conexión directa con MetaTrader 5</p>
          </button>
        </div>
      </div>

      {/* Trading Parameters */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">Parámetros de Trading</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Capital Inicial ($)</label>
            <input
              type="number"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
              className="w-full bg-dark-400 border border-gray-700 rounded-lg px-4 py-2 text-white focus:border-primary-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Riesgo por Operación (%)</label>
            <input
              type="number"
              step="0.1"
              value={riskPct}
              onChange={(e) => setRiskPct(e.target.value)}
              className="w-full bg-dark-400 border border-gray-700 rounded-lg px-4 py-2 text-white focus:border-primary-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Mín. Indicadores para Señal</label>
            <input
              type="number"
              min="1"
              max="18"
              value={minIndicators}
              onChange={(e) => setMinIndicators(e.target.value)}
              className="w-full bg-dark-400 border border-gray-700 rounded-lg px-4 py-2 text-white focus:border-primary-500 focus:outline-none"
            />
          </div>
        </div>
        <div className="mt-4 p-3 bg-dark-400 rounded-lg">
          <p className="text-sm text-gray-400">
            Riesgo monetario por operación: <span className="text-primary-400 font-medium">${riskAmount}</span>
          </p>
        </div>
        <button
          onClick={saveParameters}
          disabled={saving}
          className="btn-primary mt-4"
        >
          {saving ? 'Guardando...' : 'Guardar Parámetros'}
        </button>
      </div>

      {/* Assets Configuration */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">Activos</h2>
        
        {/* Forex */}
        <div className="mb-6">
          <h3 className="text-sm font-medium text-primary-400 mb-3">Forex</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {(availableAssets?.forex || []).map((symbol) => {
              const isActive = (availableAssets?.active || []).includes(symbol)
              return (
                <button
                  key={symbol}
                  onClick={() => toggleAsset(symbol, isActive)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-primary-500/20 text-primary-400 border border-primary-500/50'
                      : 'bg-dark-400 text-gray-500 border border-gray-700 hover:border-gray-600'
                  }`}
                >
                  {symbol}
                </button>
              )
            })}
          </div>
        </div>

        {/* Commodities */}
        <div className="mb-6">
          <h3 className="text-sm font-medium text-yellow-400 mb-3">Materias Primas</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {(availableAssets?.commodities || []).map((symbol) => {
              const isActive = (availableAssets?.active || []).includes(symbol)
              return (
                <button
                  key={symbol}
                  onClick={() => toggleAsset(symbol, isActive)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/50'
                      : 'bg-dark-400 text-gray-500 border border-gray-700 hover:border-gray-600'
                  }`}
                >
                  {symbol}
                </button>
              )
            })}
          </div>
        </div>

        {/* Indices */}
        <div>
          <h3 className="text-sm font-medium text-blue-400 mb-3">Índices</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {(availableAssets?.indices || []).map((symbol) => {
              const isActive = (availableAssets?.active || []).includes(symbol)
              return (
                <button
                  key={symbol}
                  onClick={() => toggleAsset(symbol, isActive)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/50'
                      : 'bg-dark-400 text-gray-500 border border-gray-700 hover:border-gray-600'
                  }`}
                >
                  {symbol}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Indicators Configuration */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">Indicadores Técnicos</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700/50">
                <th className="text-left py-2 px-3">Indicador</th>
                <th className="text-left py-2 px-3">Categoría</th>
                <th className="text-center py-2 px-3">Activo</th>
                <th className="text-right py-2 px-3">Peso</th>
              </tr>
            </thead>
            <tbody>
              {(config?.indicators || []).map((ind, idx) => (
                <tr key={idx} className="border-b border-gray-700/30">
                  <td className="py-2 px-3 text-white">{ind.name}</td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      ind.category === 'trend' ? 'bg-blue-500/20 text-blue-400' :
                      ind.category === 'momentum' ? 'bg-purple-500/20 text-purple-400' :
                      ind.category === 'volatility' ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-green-500/20 text-green-400'
                    }`}>
                      {ind.category}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={ind.enabled ? 'text-green-400' : 'text-red-400'}>
                      {ind.enabled ? '✓' : '✗'}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right text-gray-300">{ind.weight}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default ConfigPage
