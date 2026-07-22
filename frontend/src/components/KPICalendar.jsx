import React, { useState, useEffect, useMemo } from 'react'
import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react'
import { dashboardApi } from '../services/api'

const WEEKDAY_LABELS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
const MONTH_LABELS = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
]

/**
 * Determina el color de fondo de una celda del calendario según el P/L
 * neto del día. Sin operaciones ese día: gris neutro. Con operaciones:
 * verde (ganancia) o rojo (pérdida), con intensidad proporcional a qué
 * tan lejos está del "objetivo" implícito (se usa una escala simple
 * basada en el signo y una referencia de $50 para la intensidad, no un
 * límite duro).
 */
function getCellStyle(day) {
  if (!day || !day.total_trades) {
    return 'bg-dark-300/40 border-gray-700/30'
  }
  const netProfit = day.net_profit || 0
  if (netProfit > 0) {
    const intensity = Math.min(netProfit / 50, 1)
    if (intensity > 0.66) return 'bg-green-500/30 border-green-500/50'
    if (intensity > 0.33) return 'bg-green-500/20 border-green-500/40'
    return 'bg-green-500/10 border-green-500/30'
  }
  if (netProfit < 0) {
    const intensity = Math.min(Math.abs(netProfit) / 50, 1)
    if (intensity > 0.66) return 'bg-red-500/30 border-red-500/50'
    if (intensity > 0.33) return 'bg-red-500/20 border-red-500/40'
    return 'bg-red-500/10 border-red-500/30'
  }
  return 'bg-gray-500/15 border-gray-500/30'
}

function DayCell({ dateObj, day }) {
  const [hover, setHover] = useState(false)
  const dayNumber = dateObj.getDate()

  return (
    <div
      className={`relative border rounded-lg p-2 h-20 flex flex-col justify-between transition-colors ${getCellStyle(day)}`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <span className="text-xs text-gray-400">{dayNumber}</span>

      {day && day.total_trades > 0 && (
        <div className="text-right">
          <p className={`text-sm font-semibold ${day.net_profit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {day.net_profit >= 0 ? '+' : ''}{day.net_profit.toFixed(0)}
          </p>
          <p className="text-[10px] text-gray-400">{day.win_rate.toFixed(0)}% WR</p>
        </div>
      )}

      {hover && day && day.total_trades > 0 && (
        <div className="absolute z-10 top-full left-1/2 -translate-x-1/2 mt-1 w-48 bg-dark-200 border border-gray-700 rounded-lg shadow-xl p-3 text-xs">
          <p className="text-white font-medium mb-1">{day.date}</p>
          <div className="space-y-1 text-gray-300">
            <div className="flex justify-between"><span>Operaciones</span><span>{day.total_trades}</span></div>
            <div className="flex justify-between"><span>Ganadoras</span><span className="text-green-400">{day.wins}</span></div>
            <div className="flex justify-between"><span>Perdedoras</span><span className="text-red-400">{day.losses}</span></div>
            <div className="flex justify-between"><span>Win Rate</span><span>{day.win_rate.toFixed(1)}%</span></div>
            <div className="flex justify-between"><span>P/L Neto</span><span className={day.net_profit >= 0 ? 'text-green-400' : 'text-red-400'}>${day.net_profit.toFixed(2)}</span></div>
            <div className="flex justify-between"><span>Profit Factor</span><span>{day.profit_factor.toFixed(2)}</span></div>
          </div>
        </div>
      )}
    </div>
  )
}

function KPICalendar() {
  const [dailyData, setDailyData] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [viewDate, setViewDate] = useState(new Date())

  useEffect(() => {
    fetchDailyKPIs()
  }, [])

  const fetchDailyKPIs = async () => {
    try {
      const res = await dashboardApi.getDailyKPIs()
      setDailyData(res.data.days || [])
      setError(null)
    } catch (err) {
      setError('No se pudieron cargar los KPIs diarios')
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerate = async () => {
    setRefreshing(true)
    try {
      await dashboardApi.regenerateDailyKPIs()
      await fetchDailyKPIs()
    } catch (err) {
      setError('No se pudo regenerar el archivo de KPIs diarios')
    } finally {
      setRefreshing(false)
    }
  }

  // Indexar los KPIs diarios por fecha "YYYY-MM-DD" para lookup O(1) al construir la grilla
  const dataByDate = useMemo(() => {
    const map = {}
    dailyData.forEach((d) => { map[d.date] = d })
    return map
  }, [dailyData])

  // Totales del mes visible (para el resumen sobre el calendario)
  const monthSummary = useMemo(() => {
    const year = viewDate.getFullYear()
    const month = viewDate.getMonth()
    const monthDays = dailyData.filter((d) => {
      const [y, m] = d.date.split('-').map(Number)
      return y === year && m === month + 1
    })
    const totalTrades = monthDays.reduce((sum, d) => sum + d.total_trades, 0)
    const totalWins = monthDays.reduce((sum, d) => sum + d.wins, 0)
    const netProfit = monthDays.reduce((sum, d) => sum + d.net_profit, 0)
    const winRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0
    return { totalTrades, netProfit, winRate, tradingDays: monthDays.length }
  }, [dailyData, viewDate])

  const calendarCells = useMemo(() => {
    const year = viewDate.getFullYear()
    const month = viewDate.getMonth()
    const firstOfMonth = new Date(year, month, 1)
    // Lunes=0 ... Domingo=6 (getDay() da Domingo=0, se reindexa)
    const firstWeekday = (firstOfMonth.getDay() + 6) % 7
    const daysInMonth = new Date(year, month + 1, 0).getDate()

    const cells = []
    for (let i = 0; i < firstWeekday; i++) cells.push(null)
    for (let d = 1; d <= daysInMonth; d++) {
      const dateObj = new Date(year, month, d)
      const key = dateObj.toISOString().split('T')[0]
      cells.push({ dateObj, day: dataByDate[key] || null })
    }
    return cells
  }, [viewDate, dataByDate])

  const goToPreviousMonth = () => setViewDate(new Date(viewDate.getFullYear(), viewDate.getMonth() - 1, 1))
  const goToNextMonth = () => setViewDate(new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 1))
  const goToToday = () => setViewDate(new Date())

  if (loading) {
    return (
      <div className="card">
        <p className="text-gray-400 text-sm">Cargando calendario de KPIs...</p>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold text-white">Calendario de KPIs (corte diario)</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {monthSummary.tradingDays} día(s) con operaciones · {monthSummary.totalTrades} operaciones ·{' '}
            <span className={monthSummary.netProfit >= 0 ? 'text-green-400' : 'text-red-400'}>
              {monthSummary.netProfit >= 0 ? '+' : ''}${monthSummary.netProfit.toFixed(2)}
            </span>
            {' '}· {monthSummary.winRate.toFixed(1)}% WR
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleRegenerate}
            disabled={refreshing}
            title="Regenerar daily_kpis.xlsx ahora"
            className="p-1.5 rounded-lg bg-dark-300 hover:bg-dark-200 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          </button>
          <button onClick={goToPreviousMonth} className="p-1.5 rounded-lg bg-dark-300 hover:bg-dark-200 text-gray-400 hover:text-white transition-colors">
            <ChevronLeft size={16} />
          </button>
          <button onClick={goToToday} className="px-2 py-1 text-xs rounded-lg bg-dark-300 hover:bg-dark-200 text-gray-300 transition-colors">
            Hoy
          </button>
          <button onClick={goToNextMonth} className="p-1.5 rounded-lg bg-dark-300 hover:bg-dark-200 text-gray-400 hover:text-white transition-colors">
            <ChevronRight size={16} />
          </button>
          <span className="text-sm font-medium text-white ml-2 min-w-[130px] text-center">
            {MONTH_LABELS[viewDate.getMonth()]} {viewDate.getFullYear()}
          </span>
        </div>
      </div>

      {error && <p className="text-red-400 text-xs mb-3">{error}</p>}

      <div className="grid grid-cols-7 gap-2 mb-2">
        {WEEKDAY_LABELS.map((label) => (
          <div key={label} className="text-center text-xs text-gray-500 uppercase tracking-wide">{label}</div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-2">
        {calendarCells.map((cell, idx) =>
          cell ? (
            <DayCell key={cell.dateObj.toISOString()} dateObj={cell.dateObj} day={cell.day} />
          ) : (
            <div key={`empty-${idx}`} />
          )
        )}
      </div>

      <div className="flex items-center gap-4 mt-4 text-xs text-gray-500">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-green-500/30 border border-green-500/50 inline-block" /> Día ganador
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-red-500/30 border border-red-500/50 inline-block" /> Día perdedor
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-dark-300/40 border border-gray-700/30 inline-block" /> Sin operaciones
        </div>
      </div>
    </div>
  )
}

export default KPICalendar
