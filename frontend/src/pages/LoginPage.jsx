import React from 'react'

function LoginPage({ onLogin }) {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="card max-w-md w-full text-center">
        <div className="w-16 h-16 bg-primary-500 rounded-2xl flex items-center justify-center mx-auto mb-6">
          <span className="text-2xl font-bold text-white">TS</span>
        </div>
        
        <h1 className="text-2xl font-bold text-white mb-2">TradingSignal Pro</h1>
        <p className="text-gray-400 mb-8">
          Sistema Inteligente de Señales de Trading Multi-Activo
        </p>

        <button
          onClick={onLogin}
          className="w-full flex items-center justify-center space-x-3 bg-white text-gray-800 font-medium py-3 px-6 rounded-lg hover:bg-gray-100 transition-colors"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          <span>Iniciar sesión con Google</span>
        </button>

        <p className="text-xs text-gray-500 mt-6">
          Se requiere autenticación para enviar reportes por correo electrónico
        </p>

        <div className="mt-8 pt-6 border-t border-gray-700/50">
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-lg font-bold text-primary-400">18</p>
              <p className="text-xs text-gray-500">Indicadores</p>
            </div>
            <div>
              <p className="text-lg font-bold text-primary-400">12</p>
              <p className="text-xs text-gray-500">Activos</p>
            </div>
            <div>
              <p className="text-lg font-bold text-primary-400">75%</p>
              <p className="text-xs text-gray-500">Win Rate Obj.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default LoginPage
