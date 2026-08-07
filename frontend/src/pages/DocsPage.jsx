import React, { useState } from 'react'

// CAMBIO (a pedido del usuario): página de referencia que muestra, dentro
// del propio dashboard, los dos documentos de origen usados para migrar el
// motor de señales de indicadores a estrategias:
//   - Estrategias.html      -> manual completo de las 18 estrategias SMC/ICT
//   - Tablas_de_aplicacion.html -> tabla de activos y estrategias óptimas por grupo
// Los archivos se sirven como estáticos desde /docs/ (frontend/public/docs/),
// así que no requieren backend ni build adicional -- ver REEMPLAZOS.md.
const DOCS = [
  { key: 'tablas', label: 'Tabla de Activos y Estrategias', src: '/docs/Tablas_de_aplicacion.html' },
  { key: 'estrategias', label: 'Manual de las 18 Estrategias', src: '/docs/Estrategias.html' },
]

// Mapeo activo -> grupo -> estrategias, para mostrar un resumen rápido sin
// tener que abrir el manual completo. Debe mantenerse en sincronía manual
// con ASSET_GROUPS en app/services/strategy_engine.py si se edita ahí.
const ASSET_GROUPS_SUMMARY = [
  { group: 'Divisas: Majors', assets: 'EURUSD, GBPUSD, USDCHF, NZDUSD', strategies: 'Estrategia 1 (Silver Bullet) + Estrategia 4 (Breakout Institucional)' },
  { group: 'Divisas: Yen & Commodity', assets: 'USDJPY, AUDUSD, USDCAD', strategies: 'Estrategia 5 (Pullback EMA) + Estrategia 6 (Cruce de EMAs)' },
  { group: 'Divisas: Cruces / Minors', assets: 'EURGBP, EURJPY, EURCHF, GBPJPY, CHFJPY, AUDJPY, CADJPY, NZDJPY, AUDNZD, AUDCHF, GBPCHF, CADCHF', strategies: 'Estrategia 3 (Trampa Rango Asiático / AMD) + Estrategia 18 (S/R Dinámica)' },
  { group: 'Índices Bursátiles', assets: 'US30Cash, US500Cash, US100Cash, GER40Cash, STOXX50Cash', strategies: 'Estrategia 16 (Volumen con Acumulación) + Estrategia 3 (AMD en apertura)' },
  { group: 'Metales y Materias Primas', assets: 'XAUUSD, WTI, BRENT, COPPER', strategies: 'Estrategia 8 (Bollinger) + Estrategia 5 (Pullback EMA)' },
]

function DocsPage() {
  const [active, setActive] = useState(DOCS[0].key)
  const current = DOCS.find((d) => d.key === active)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">Documentación de Estrategias</h1>
        <p className="text-sm text-gray-400 mt-1">
          Referencia usada por el motor de señales: manual de las 18 estrategias SMC/ICT y la tabla de
          asignación de estrategias por grupo de activo. El motor real vive en
          <code className="mx-1 px-1 bg-dark-200 rounded">app/services/strategy_engine.py</code>.
        </p>
      </div>

      {/* Resumen rápido del mapeo activo -> estrategias */}
      <div className="bg-dark-200 border border-gray-700/50 rounded-xl overflow-x-auto">
        <table className="min-w-full text-sm text-left">
          <thead className="text-gray-400 uppercase text-xs bg-dark-300/50">
            <tr>
              <th className="px-4 py-3">Grupo de Activo</th>
              <th className="px-4 py-3">Activos</th>
              <th className="px-4 py-3">Estrategias Asignadas (máx. 2)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700/50 text-gray-300">
            {ASSET_GROUPS_SUMMARY.map((row) => (
              <tr key={row.group}>
                <td className="px-4 py-3 font-medium text-white whitespace-nowrap">{row.group}</td>
                <td className="px-4 py-3 text-primary-400">{row.assets}</td>
                <td className="px-4 py-3 text-gray-400">{row.strategies}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Tabs para los documentos completos */}
      <div className="flex space-x-2 border-b border-gray-700/50">
        {DOCS.map((doc) => (
          <button
            key={doc.key}
            onClick={() => setActive(doc.key)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              active === doc.key
                ? 'bg-dark-200 text-primary-400 border border-b-0 border-gray-700/50'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {doc.label}
          </button>
        ))}
        <a
          href={current.src}
          target="_blank"
          rel="noreferrer"
          className="ml-auto px-3 py-2 text-xs text-gray-400 hover:text-white self-center"
        >
          Abrir en pestaña nueva ↗
        </a>
      </div>

      <div className="bg-dark-200 border border-gray-700/50 rounded-xl overflow-hidden" style={{ height: '75vh' }}>
        <iframe
          key={current.key}
          title={current.label}
          src={current.src}
          className="w-full h-full"
          style={{ border: 'none' }}
        />
      </div>
    </div>
  )
}

export default DocsPage
