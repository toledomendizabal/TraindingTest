//+------------------------------------------------------------------+
//|                                              PriceExporter.mq5   |
//|                                  Copyright 2026, TradingSignalPro|
//|                                             https://manus.im     |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TradingSignalPro"
#property link      "https://manus.im"
#property version   "2.20"
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

// V2.2 (2026-10-01) -- simbolos con sufijo del broker ("..."):
//
// Tras reinstalar el ambiente, el broker (MEXAtlantic-Demo) publica casi todos
// los instrumentos con sufijo "..." (EURUSD..., XAUUSD..., etc.) y el
// historial no se generaba para ellos. Cambios:
//
// 1) AUTO-SELECCION POR SUFIJO: al iniciar y en cada ciclo de historial, el EA
//    recorre TODOS los simbolos del servidor (SymbolsTotal(false)) y agrega al
//    Market Watch los que terminan en SymbolSuffix. Antes solo exportaba lo
//    que alguien hubiera agregado a mano (o lo de SymbolsToExport).
// 2) NO SE SALTA EN SILENCIO: un simbolo sin historial sincronizado ya no se
//    descarta sin aviso. Se fuerza la descarga con CopyRates y, mientras falten
//    datos, el ciclo de historial se repite cada HistoryRetrySeconds (30s) en
//    vez de esperar 300s. Se registra en el log de Expertos cuales faltan.
// 3) NO SE ESCRIBEN ARCHIVOS VACIOS: primero se copian las velas y solo si hay
//    datos se abre/escribe el archivo. Si FileOpen falla se imprime el error.
// 4) NUEVO history_<simbolo>_1d.csv (D1): el backend pide "1d" para el filtro
//    de tendencia macro (_validate_macro_trend); como ese archivo no existia,
//    caia al archivo base de 1 minuto (EMA50 "diaria" calculada sobre velas
//    de M1). Controlado por ExportDailyHistory.
//    Opcional: history_<simbolo>_5m.csv con ExportM5History (apagado por
//    defecto: hoy el backend pide "5m" y recibe M1; activarlo cambia la
//    senal a velas reales de 5 minutos).
// 5) El temporizador del historial usa TimeLocal() en vez de TimeCurrent():
//    con el mercado cerrado (fin de semana) TimeCurrent() no avanza y el
//    historial nunca se refrescaba.
// 6) Nombres de archivo: ademas de "/" y "\\" se sanean : * ? " < > |
//    (los puntos del sufijo "..." son validos: history_EURUSD....csv).
//
input int ExportIntervalSeconds = 1;          // Precio en tiempo real
input int HistoryExportIntervalSeconds = 300; // Historial (antes: igual a ExportIntervalSeconds, cada 1s)
input int HistoryBars = 1000;                 // Number of bars to export for indicators and Night-Watch
input string SymbolsToExport = "US500Cash,US30Cash,US100Cash,GER40Cash,STOXX50Cash"; // CSV explicito de simbolos que deben exportarse SIEMPRE, ademas del Market Watch. Ajustar al nombre EXACTO que use este broker.
input string SymbolSuffix = "...";            // Sufijo del broker: todo simbolo del servidor que termine asi se agrega al Market Watch y se exporta
input bool   AutoSelectSuffixSymbols = true;  // Agregar automaticamente al Market Watch los simbolos con SymbolSuffix
input int    MaxSuffixSymbols = 100;          // Tope de simbolos auto-agregados (protege la terminal si el broker tiene cientos con ese sufijo)
input int    HistoryRetrySeconds = 30;        // Reintento del historial mientras haya simbolos sin datos sincronizados
input bool   ExportDailyHistory = true;       // Escribe history_<simbolo>_1d.csv (lo pide el filtro de tendencia macro)
input bool   ExportM5History = false;         // Escribe history_<simbolo>_5m.csv (si es false el backend usa el archivo base de M1 para "5m")

datetime g_last_history_export = 0;
bool     g_history_incomplete = false;   // true si en el ultimo ciclo faltaron datos de algun simbolo
string   g_last_summary = "";            // evita repetir el mismo resumen en el log


//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   EnsureRequiredSymbolsSelected();
   SelectSuffixSymbols();
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
//| true si name termina exactamente en suffix                       |
//+------------------------------------------------------------------+
bool HasSuffix(const string name, const string suffix)
{
   int ln = StringLen(name);
   int ls = StringLen(suffix);
   if(ls == 0 || ln < ls) return(false);
   return(StringSubstr(name, ln - ls) == suffix);
}

//+------------------------------------------------------------------+
//| Nombre de simbolo seguro para usar dentro de un nombre de archivo |
//+------------------------------------------------------------------+
string SafeFileSymbol(string symbol)
{
   StringReplace(symbol, "/", "");
   StringReplace(symbol, "\\", "");
   StringReplace(symbol, ":", "");
   StringReplace(symbol, "*", "");
   StringReplace(symbol, "?", "");
   StringReplace(symbol, "\"", "");
   StringReplace(symbol, "<", "");
   StringReplace(symbol, ">", "");
   StringReplace(symbol, "|", "");
   return(symbol);
}

//+------------------------------------------------------------------+
//| Agrega al Market Watch todo simbolo del servidor que termine en  |
//| SymbolSuffix (hasta MaxSuffixSymbols). Idempotente.              |
//+------------------------------------------------------------------+
void SelectSuffixSymbols()
{
   if(!AutoSelectSuffixSymbols || StringLen(SymbolSuffix) == 0) return;

   int total = SymbolsTotal(false);   // false = TODOS los simbolos del servidor
   int matched = 0, added = 0;
   for(int i = 0; i < total; i++)
   {
      string name = SymbolName(i, false);
      if(!HasSuffix(name, SymbolSuffix)) continue;

      matched++;
      if(matched > MaxSuffixSymbols)
      {
         Print("PriceExporter: se alcanzo MaxSuffixSymbols=", MaxSuffixSymbols,
               "; se ignoran los simbolos con sufijo '", SymbolSuffix, "' restantes.");
         break;
      }
      if(SymbolInfoInteger(name, SYMBOL_SELECT)) continue;   // ya estaba en Market Watch

      if(SymbolSelect(name, true)) added++;
      else Print("PriceExporter: no se pudo agregar '", name, "' al Market Watch (error ", GetLastError(), ").");
   }
   if(added > 0)
      Print("PriceExporter: ", added, " simbolo(s) con sufijo '", SymbolSuffix,
            "' agregado(s) al Market Watch (", matched, " con ese sufijo en el servidor).");
}

//+------------------------------------------------------------------+
//| Timer function                                                   |
//+------------------------------------------------------------------+
void OnTimer()
{
   ExportRealTimePrices();
   ExportHeartbeat();

   // TimeLocal(): TimeCurrent() no avanza con el mercado cerrado.
   datetime now = TimeLocal();
   int interval = g_history_incomplete ? HistoryRetrySeconds : HistoryExportIntervalSeconds;
   if(now - g_last_history_export >= interval)
   {
      SelectSuffixSymbols();
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

// Devuelve true si el archivo se escribio con al menos una vela.
bool ExportHistoryFile(string symbol, string safe_symbol, ENUM_TIMEFRAMES period, string suffix)
{
   // 1) Copiar primero: si no hay datos NO se toca el archivo existente ni se crea uno vacio.
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, period, 0, HistoryBars, rates);
   if(copied <= 0) return(false);

   string fileName = "history_" + safe_symbol + suffix + ".csv";
   int handle = FileOpen(fileName, FILE_CSV|FILE_WRITE|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON|FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("PriceExporter: no se pudo abrir '", fileName, "' (error ", GetLastError(), ")");
      return(false);
   }

   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   FileWrite(handle, "datetime", "open", "high", "low", "close", "volume");
   for(int j = 0; j < copied; j++)
   {
      FileWrite(handle,
         TimeToString(rates[j].time, TIME_DATE|TIME_SECONDS),
         DoubleToString(rates[j].open, digits),
         DoubleToString(rates[j].high, digits),
         DoubleToString(rates[j].low, digits),
         DoubleToString(rates[j].close, digits),
         (string)rates[j].tick_volume);
   }
   FileClose(handle);
   return(true);
}

void ExportHistory()
{
   int total = SymbolsTotal(true);
   int ok_count = 0;
   string missing = "";
   int missing_count = 0;

   for(int i = 0; i < total; i++)
   {
      string symbol = SymbolName(i, true);
      string safe_symbol = SafeFileSymbol(symbol);

      // Sin historial sincronizado: se fuerza la descarga con CopyRates (la primera
      // llamada la dispara y devuelve <=0); el reintento corto la recoge despues.
      // Antes el simbolo se saltaba sin dejar rastro.
      bool ready = (bool)SeriesInfoInteger(symbol, PERIOD_M1, SERIES_SYNCHRONIZED);
      MqlRates probe[];
      if(!ready && CopyRates(symbol, PERIOD_M1, 0, 1, probe) <= 0)
      {
         missing_count++;
         if(StringLen(missing) < 400) missing += symbol + " ";
         continue;
      }

      // Export different timeframes for full structural validation
      bool wrote = ExportHistoryFile(symbol, safe_symbol, PERIOD_M1, "");      // Base (M1)
      ExportHistoryFile(symbol, safe_symbol, PERIOD_M30, "_30m");              // Structural 30m
      ExportHistoryFile(symbol, safe_symbol, PERIOD_H1,  "_1h");               // HTF 1h
      ExportHistoryFile(symbol, safe_symbol, PERIOD_H4,  "_4h");               // HTF 4h
      if(ExportDailyHistory) ExportHistoryFile(symbol, safe_symbol, PERIOD_D1, "_1d"); // Macro trend
      if(ExportM5History)    ExportHistoryFile(symbol, safe_symbol, PERIOD_M5, "_5m"); // Senal 5m real

      if(wrote) ok_count++;
      else { missing_count++; if(StringLen(missing) < 400) missing += symbol + " "; }
   }

   g_history_incomplete = (missing_count > 0);

   string summary = "historial OK en " + (string)ok_count + " de " + (string)total + " simbolos";
   if(missing_count > 0)
      summary += "; SIN DATOS (se reintenta cada " + (string)HistoryRetrySeconds + "s): " + missing;
   if(summary != g_last_summary)
   {
      Print("PriceExporter: ", summary);
      g_last_summary = summary;
   }
}
