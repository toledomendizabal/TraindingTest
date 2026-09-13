//+------------------------------------------------------------------+
//|                                              PriceExporter.mq5   |
//|                                  Copyright 2026, TradingSignalPro|
//|                                             https://manus.im     |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TradingSignalPro"
#property link      "https://manus.im"
#property version   "2.10"
#property strict

// V2.0: Exports Real-time prices AND Candle History for analysis.
// Python will prioritize these files over Twelve Data API.
//
// V2.1 (fix, 2026-09-12) -- cambios a partir del diagnostico de
// errors_2026-09-*.log y monitoring_2026-09-*.log reales:
//
// 1) SYMBOLS EXPLICITOS: la version anterior usaba SymbolsTotal(true),
//    es decir, SOLO exportaba lo que ya estuviera agregado a mano en el
//    Market Watch de la terminal. Si un simbolo requerido por el motor de
//    senales (ej. el indice que el backend llama "US500Cash") no estaba
//    en el Market Watch de esta cuenta/broker, el EA nunca lo exportaba y
//    nunca daba error -- simplemente no aparecia el archivo, lo que en
//    monitoring_2026-09-10.log se ve como cientos de
//    "No price data available for US500Cash during monitoring" seguidos.
//    Ahora el EA fuerza SymbolSelect() de una lista explicita
//    (SymbolsToExport) al iniciar, ademas de lo que ya este en Market
//    Watch, para no depender de que alguien lo agregue a mano en cada
//    instalacion nueva.
//
// 2) FRECUENCIA SEPARADA: exportar el historial completo (por defecto
//    1000 velas x 4 timeframes x N simbolos) CADA 1 SEGUNDO, igual que el
//    precio en tiempo real, es un costo de E/S innecesario (reescribe
//    miles de filas por segundo sin que ese detalle cambie de un segundo
//    a otro) que puede degradar la terminal en sesiones largas. Ahora el
//    historial se exporta cada HistoryExportIntervalSeconds (300s por
//    defecto) y el precio en tiempo real sigue cada ExportIntervalSeconds
//    (1s), que es lo que de verdad necesita esa cadencia.
//
// 3) HEARTBEAT: se agrega "ea_heartbeat.csv" con timestamp del ultimo
//    ciclo y el estado de AutoTrading/trading permitido de la CUENTA
//    (no de la sesion Python -- esto es independiente y sirve para
//    diagnosticar incluso si el backend Python no esta corriendo en ese
//    momento). Permite a Python (o a cualquier monitor externo) detectar
//    si este EA dejo de correr o si AutoTrading se desactivo, con solo
//    leer un CSV, sin depender de la libreria MetaTrader5 de Python.

input int ExportIntervalSeconds = 1;          // Precio en tiempo real
input int HistoryExportIntervalSeconds = 300; // Historial (antes: igual a ExportIntervalSeconds, cada 1s)
input int HistoryBars = 1000;                 // Number of bars to export for indicators and Night-Watch
input string SymbolsToExport = "US500Cash,US30Cash,US100Cash,GER40Cash,STOXX50Cash"; // CSV explicito de simbolos que deben exportarse SIEMPRE, ademas del Market Watch. Ajustar al nombre EXACTO que use este broker.

datetime g_last_history_export = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   EnsureRequiredSymbolsSelected();
   EventSetTimer(ExportIntervalSeconds);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { EventKillTimer(); }

//+------------------------------------------------------------------+
//| Fuerza que los simbolos de SymbolsToExport esten en Market Watch |
//| (fix 2026-09-12): antes, si no estaban ya agregados a mano en    |
//| esta terminal, jamas se exportaban ni se avisaba por que.        |
//+------------------------------------------------------------------+
void EnsureRequiredSymbolsSelected()
{
   string parts[];
   int n = StringSplit(SymbolsToExport, ',', parts);
   for(int i = 0; i < n; i++)
   {
      string sym = parts[i];
      StringTrimLeft(sym);
      StringTrimRight(sym);
      if(sym == "") continue;

      if(!SymbolSelect(sym, true))
      {
         Print("PriceExporter: no se pudo seleccionar el simbolo '", sym,
               "' -- verifica que el nombre coincida EXACTO con el que usa este broker "
               "(revisa el Market Watch completo, boton derecho > 'Mostrar todo').");
      }
   }
}

//+------------------------------------------------------------------+
//| Timer function                                                   |
//+------------------------------------------------------------------+
void OnTimer()
{
   ExportRealTimePrices();
   ExportHeartbeat();

   datetime now = TimeCurrent();
   if(now - g_last_history_export >= HistoryExportIntervalSeconds)
   {
      ExportHistory();
      g_last_history_export = now;
   }
}

void ExportRealTimePrices()
{
   string FileName = "mt4_prices.csv";
   int handle = FileOpen(FileName, FILE_CSV|FILE_WRITE|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON|FILE_ANSI, ',');
   if(handle != INVALID_HANDLE)
   {
      FileWrite(handle, "Symbol", "Bid", "Ask", "Time");
      int total = SymbolsTotal(true);
      for(int i=0; i<total; i++)
      {
         string symbol = SymbolName(i, true);
         MqlTick last_tick;
         if(SymbolInfoTick(symbol, last_tick))
         {
            FileWrite(handle, symbol, 
               DoubleToString(last_tick.bid, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)), 
               DoubleToString(last_tick.ask, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
               TimeToString(last_tick.time, TIME_DATE|TIME_SECONDS));
         }
      }
      FileClose(handle);
   }
}

//+------------------------------------------------------------------+
//| NUEVO (fix 2026-09-12): heartbeat legible por Python o por        |
//| cualquier monitor externo sin pasar por la libreria MetaTrader5.  |
//| Resuelve el pedido de "verificar que los servicios esten          |
//| disponibles": esto es la mitad que corre DENTRO de la terminal    |
//| (AutoTrading/trading de cuenta); la mitad que corre en Python     |
//| (conexion IPC) ya la cubre mt5_executor.get_health_status().      |
//+------------------------------------------------------------------+
void ExportHeartbeat()
{
   string FileName = "ea_heartbeat.csv";
   int handle = FileOpen(FileName, FILE_CSV|FILE_WRITE|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON|FILE_ANSI, ',');
   if(handle != INVALID_HANDLE)
   {
      FileWrite(handle, "timestamp_utc", "autotrading_terminal", "trade_allowed_account", "connected");
      FileWrite(handle,
         TimeToString(TimeGMT(), TIME_DATE|TIME_SECONDS),
         (string)(int)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED),
         (string)(int)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED),
         (string)(int)TerminalInfoInteger(TERMINAL_CONNECTED));
      FileClose(handle);
   }
}

void ExportHistoryFile(string symbol, string safe_symbol, ENUM_TIMEFRAMES period, string suffix)
{
   string fileName = "history_" + safe_symbol + suffix + ".csv";
   int handle = FileOpen(fileName, FILE_CSV|FILE_WRITE|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON|FILE_ANSI, ',');
   
   if(handle != INVALID_HANDLE)
   {
      FileWrite(handle, "datetime", "open", "high", "low", "close", "volume");
      
      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      int copied = CopyRates(symbol, period, 0, HistoryBars, rates);
      
      for(int j=0; j<copied; j++)
      {
         FileWrite(handle, 
            TimeToString(rates[j].time, TIME_DATE|TIME_SECONDS),
            DoubleToString(rates[j].open, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
            DoubleToString(rates[j].high, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
            DoubleToString(rates[j].low, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
            DoubleToString(rates[j].close, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
            (string)rates[j].tick_volume);
      }
      FileClose(handle);
   }
}

void ExportHistory()
{
   int total = SymbolsTotal(true);
   for(int i=0; i<total; i++)
   {
      string symbol = SymbolName(i, true);
      string safe_symbol = symbol;
      StringReplace(safe_symbol, "/", "");
      StringReplace(safe_symbol, "\\", "");
      
      if(!SymbolIsSynchronized(symbol)) continue;

      // Export different timeframes for full structural validation
      ExportHistoryFile(symbol, safe_symbol, PERIOD_M1, "");      // Default (1m/5m context)
      ExportHistoryFile(symbol, safe_symbol, PERIOD_M30, "_30m"); // Structural 30m
      ExportHistoryFile(symbol, safe_symbol, PERIOD_H1, "_1h");   // HTF 1h
      ExportHistoryFile(symbol, safe_symbol, PERIOD_H4, "_4h");   // HTF 4h
   }
}
