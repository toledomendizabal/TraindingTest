//+------------------------------------------------------------------+
//|                                              PriceExporter.mq4   |
//|                                  Copyright 2026, TradingSignalPro|
//|                                             https://manus.im     |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TradingSignalPro"
#property link      "https://manus.im"
#property version   "1.00"
#property strict

// This EA exports prices of all symbols in Market Watch to a CSV file
// located in the Common/Files folder for the Python system to read.

input int ExportIntervalSeconds = 1; // Export interval in seconds

string FileName = "mt4_prices.csv";

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(ExportIntervalSeconds);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
}

//+------------------------------------------------------------------+
//| Timer function                                                   |
//+------------------------------------------------------------------+
void OnTimer()
{
   int handle = FileOpen(FileName, FILE_CSV|FILE_WRITE|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON, ',');
   if(handle != INVALID_HANDLE)
   {
      FileWrite(handle, "Symbol", "Bid", "Ask");
      
      int total = SymbolsTotal(true);
      for(int i=0; i<total; i++)
      {
         string symbol = SymbolName(i, true);
         double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
         double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
         
         FileWrite(handle, symbol, DoubleToString(bid, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)), DoubleToString(ask, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)));
      }
      
      FileClose(handle);
   }
}
//+------------------------------------------------------------------+
