import axios from 'axios'

const API_BASE = '/api'

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// WebSocket connection
export function createWebSocket(path = '/ws/live') {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return new WebSocket(`${protocol}//${host}/api${path}`)
}

// API endpoints
export const signalsApi = {
  getActive: () => api.get('/signals/active'),
  getAll: () => api.get('/signals/all'),
  getClosed: (startDate) => api.get('/signals/closed', { params: { start_date: startDate } }),
  triggerAnalysis: () => api.post('/signals/analyze'),
  analyzeAsset: (asset) => api.post(`/signals/analyze/${asset}`),
  getStatistics: () => api.get('/signals/statistics')
}

export const dashboardApi = {
  getOverview: () => api.get('/dashboard/overview'),
  getKPIs: () => api.get('/dashboard/kpis'),
  getSchedulerStatus: () => api.get('/dashboard/scheduler/status'),
  getLogs: (lines = 50) => api.get('/dashboard/logs', { params: { lines } })
}

export const configApi = {
  getCurrent: () => api.get('/config/current'),
  update: (config) => api.put('/config/update', config),
  toggleAsset: (symbol, active) => api.post('/config/assets/toggle', { symbol, active }),
  getAvailableAssets: () => api.get('/config/available-assets'),
  getTradingMode: () => api.get('/config/trading-mode'),
  setTradingMode: (mode) => api.put('/config/trading-mode', null, { params: { mode } })
}

export const backtestingApi = {
  getReports: () => api.get('/backtesting/reports'),
  getLatestReport: (type = 'daily') => api.get('/backtesting/report/latest', { params: { report_type: type } }),
  runDaily: () => api.post('/backtesting/run/daily'),
  runWeekly: () => api.post('/backtesting/run/weekly')
}

export const authApi = {
  getStatus: () => api.get('/auth/status'),
  login: () => api.post('/auth/login'),
  logout: () => api.post('/auth/logout')
}
