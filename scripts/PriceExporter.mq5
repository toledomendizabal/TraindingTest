//+------------------------------------------------------------------+
//|                                              PriceExporter.mq5   |
//|                                  Copyright 2026, TradingSignalPro|
//|                                             https://manus.im     |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TradingSignalPro"
#property link      "https://manus.im"
#property version   "2.00"
#property strict

// V2.0: Exports Real-time prices AND Candle History for analysis.
// Python will prioritize these files over Twelve Data API.

input int ExportIntervalSeconds = 1; 
input int HistoryBars = 1000;        // Number of bars to export for indicators and Night-Watch

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(ExportIntervalSeconds);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { EventKillTimer(); }

//+------------------------------------------------------------------+
//| Timer function                                                   |
//+------------------------------------------------------------------+
void OnTimer()
{
   ExportRealTimePrices();
   ExportHistory();
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

void ExportHistory()
{
   int total = SymbolsTotal(true);
   for(int i=0; i<total; i++)
   {
      string symbol = SymbolName(i, true);
      string safe_symbol = symbol;
      StringReplace(safe_symbol, "/", "");
      StringReplace(safe_symbol, "\\", "");
      
      string fileName = "history_" + safe_symbol + ".csv";
      
      // Ensure data is synchronized before copying
      if(!SymbolIsSynchronized(symbol)) continue;

      int handle = FileOpen(fileName, FILE_CSV|FILE_WRITE|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON|FILE_ANSI, ',');
      
      if(handle != INVALID_HANDLE)
      {
         FileWrite(handle, "datetime", "open", "high", "low", "close", "volume");
         
         MqlRates rates[];
         ArraySetAsSeries(rates, true);
         
         // Force PERIOD_M1 for Night-Watch retroactive verification
         int copied = CopyRates(symbol, PERIOD_M1, 0, HistoryBars, rates);
         
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
}
