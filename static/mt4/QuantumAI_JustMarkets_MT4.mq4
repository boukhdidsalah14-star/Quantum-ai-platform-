//+------------------------------------------------------------------+
//| QUANTUM AI - JustMarkets MT4 bridge (demo-first)                 |
//| Install in MT4: MQL4/Experts/ and compile with MetaEditor.        |
//| This EA refuses live accounts. It syncs positions and quotes;    |
//| demo orders require both EA input and server-side demo switches. |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "Customer-isolated QUANTUM AI JustMarkets MT4 bridge"

input string ApiBaseUrl = "https://quantum-ai-platform-62cz.onrender.com";
input string BridgeToken = "";
input int ExpectedAccountLogin = 0;
input string ExpectedServer = "";
input int SyncIntervalSeconds = 5;
input ENUM_TIMEFRAMES ChartTimeframe = PERIOD_M15;
input int CandleSyncIntervalSeconds = 30;
input int CandleCount = 100;

datetime lastCandleSync = 0;

string Symbols[10] = {
   "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
   "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "XAUUSD"
};

bool IsAllowedSymbol(string symbol)
{
   for(int i=0; i<ArraySize(Symbols); i++)
      if(symbol == Symbols[i]) return true;
   return false;
}

bool IsJustMarketsCompany()
{
   string company = AccountCompany();
   StringToLower(company);
   return (StringFind(company, "justmarkets") >= 0 ||
           StringFind(company, "just global markets") >= 0);
}

bool AccountIsExpected()
{
   if(!IsDemo()) return false;
   if(AccountNumber() != ExpectedAccountLogin) return false;
   if(AccountServer() != ExpectedServer) return false;
   if(!IsJustMarketsCompany()) return false;
   return true;
}

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", "");
   StringReplace(value, "\n", " ");
   return value;
}

string UrlEncode(string value)
{
   string out = "";
   for(int i=0; i<StringLen(value); i++)
   {
      ushort ch = StringGetCharacter(value, i);
      bool safe = ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') ||
                   (ch >= '0' && ch <= '9') || ch == '-' || ch == '_' ||
                   ch == '.' || ch == '~');
      if(safe) out += CharToString((uchar)ch);
      else out += "%" + StringFormat("%02X", (int)ch);
   }
   return out;
}

bool HttpRequest(string method, string path, string body, string &response)
{
   string headers = "Authorization: Bearer " + BridgeToken + "\r\n";
   headers += "Content-Type: application/json\r\n";
   char data[];
   if(body != "")
   {
      int copied = StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
      if(copied > 0) ArrayResize(data, copied - 1);
   }
   else ArrayResize(data, 0);

   char result[];
   string resultHeaders = "";
   ResetLastError();
   int status = WebRequest(method, ApiBaseUrl + path, "", headers, 10000,
                           data, ArraySize(data), result, resultHeaders);
   if(status == -1)
   {
      Print("QUANTUM AI WebRequest failed. Error=", GetLastError(),
            ". Add the API domain to MT4 WebRequest allowlist.");
      return false;
   }
   response = CharArrayToString(result, 0, -1, CP_UTF8);
   if(status < 200 || status >= 300)
   {
      Print("QUANTUM AI HTTP status ", status, ": ", response);
      return false;
   }
   return true;
}

string BuildSyncPayload()
{
   string positions = "";
   int count = 0;
   for(int i=0; i<OrdersTotal(); i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL) continue;
      string symbol = OrderSymbol();
      if(!IsAllowedSymbol(symbol)) continue;
      if(count > 0) positions += ",";
      string side = (type == OP_BUY ? "BUY" : "SELL");
      double current = (type == OP_BUY ? MarketInfo(symbol, MODE_BID) : MarketInfo(symbol, MODE_ASK));
      positions += "{";
      positions += "\"ticket\":" + IntegerToString(OrderTicket()) + ",";
      positions += "\"symbol\":\"" + JsonEscape(symbol) + "\",";
      positions += "\"side\":\"" + side + "\",";
      positions += "\"lots\":" + DoubleToString(OrderLots(), 2) + ",";
      positions += "\"open_price\":" + DoubleToString(OrderOpenPrice(), (int)MarketInfo(symbol, MODE_DIGITS)) + ",";
      positions += "\"current_price\":" + DoubleToString(current, (int)MarketInfo(symbol, MODE_DIGITS)) + ",";
      positions += "\"stop_loss\":" + DoubleToString(OrderStopLoss(), (int)MarketInfo(symbol, MODE_DIGITS)) + ",";
      positions += "\"take_profit\":" + DoubleToString(OrderTakeProfit(), (int)MarketInfo(symbol, MODE_DIGITS)) + ",";
      positions += "\"profit\":" + DoubleToString(OrderProfit(), 2) + ",";
      positions += "\"swap\":" + DoubleToString(OrderSwap(), 2) + ",";
      positions += "\"commission\":" + DoubleToString(OrderCommission(), 2) + ",";
      positions += "\"open_time\":" + IntegerToString((int)OrderOpenTime()) + ",";
      positions += "\"magic\":" + IntegerToString(OrderMagicNumber());
      positions += "}";
      count++;
   }

   string quotes = "";
   int quoteCount = 0;
   for(int j=0; j<ArraySize(Symbols); j++)
   {
      string sym = Symbols[j];
      double bid = MarketInfo(sym, MODE_BID);
      double ask = MarketInfo(sym, MODE_ASK);
      if(bid <= 0 || ask <= 0 || ask < bid) continue;
      if(quoteCount > 0) quotes += ",";
      quotes += "\"" + sym + "\":{\"bid\":" + DoubleToString(bid, (int)MarketInfo(sym, MODE_DIGITS)) +
                ",\"ask\":" + DoubleToString(ask, (int)MarketInfo(sym, MODE_DIGITS)) + "}";
      quoteCount++;
   }

   string payload = "{";
   payload += "\"account_login\":\"" + IntegerToString(AccountNumber()) + "\",";
   payload += "\"account_server\":\"" + JsonEscape(AccountServer()) + "\",";
   payload += "\"company\":\"" + JsonEscape(AccountCompany()) + "\",";
   payload += "\"balance\":" + DoubleToString(AccountBalance(), 2) + ",";
   payload += "\"equity\":" + DoubleToString(AccountEquity(), 2) + ",";
   payload += "\"currency\":\"" + JsonEscape(AccountCurrency()) + "\",";
   payload += "\"positions\":[" + positions + "],";
   payload += "\"quotes\":{" + quotes + "}";
   payload += "}";
   return payload;
}

string TimeframeString()
{
   if(ChartTimeframe == PERIOD_M1) return "1m";
   if(ChartTimeframe == PERIOD_M5) return "5m";
   if(ChartTimeframe == PERIOD_M15) return "15m";
   if(ChartTimeframe == PERIOD_M30) return "30m";
   if(ChartTimeframe == PERIOD_H1) return "1h";
   if(ChartTimeframe == PERIOD_H4) return "4h";
   if(ChartTimeframe == PERIOD_D1) return "1d";
   return "";
}

bool SyncSymbolCandles(string symbol)
{
   string timeframe = TimeframeString();
   if(timeframe == "") return false;
   int wanted = MathMax(50, MathMin(CandleCount, 200));
   int bars = iBars(symbol, ChartTimeframe);
   if(bars < 50) return false;
   int count = MathMin(wanted, bars);
   string candles = "";
   int added = 0;
   for(int shift=count-1; shift>=0; shift--)
   {
      datetime candleTime = iTime(symbol, ChartTimeframe, shift);
      double openPrice = iOpen(symbol, ChartTimeframe, shift);
      double highPrice = iHigh(symbol, ChartTimeframe, shift);
      double lowPrice = iLow(symbol, ChartTimeframe, shift);
      double closePrice = iClose(symbol, ChartTimeframe, shift);
      long volume = iVolume(symbol, ChartTimeframe, shift);
      if(candleTime <= 0 || openPrice <= 0 || highPrice <= 0 || lowPrice <= 0 || closePrice <= 0)
         continue;
      if(added > 0) candles += ",";
      int digits = (int)MarketInfo(symbol, MODE_DIGITS);
      candles += "{";
      candles += "\"time\":" + IntegerToString((int)candleTime) + ",";
      candles += "\"open\":" + DoubleToString(openPrice, digits) + ",";
      candles += "\"high\":" + DoubleToString(highPrice, digits) + ",";
      candles += "\"low\":" + DoubleToString(lowPrice, digits) + ",";
      candles += "\"close\":" + DoubleToString(closePrice, digits) + ",";
      candles += "\"volume\":" + IntegerToString((int)volume);
      candles += "}";
      added++;
   }
   if(added < 50) return false;
   string body = "{";
   body += "\"account_login\":\"" + IntegerToString(AccountNumber()) + "\",";
   body += "\"account_server\":\"" + JsonEscape(AccountServer()) + "\",";
   body += "\"company\":\"" + JsonEscape(AccountCompany()) + "\",";
   body += "\"symbol\":\"" + symbol + "\",";
   body += "\"timeframe\":\"" + timeframe + "\",";
   body += "\"candles\":[" + candles + "]";
   body += "}";
   string response = "";
   return HttpRequest("POST", "/api/mt4/bridge/candles", body, response);
}

void SyncAllMarketCandles()
{
   for(int i=0; i<ArraySize(Symbols); i++)
      SyncSymbolCandles(Symbols[i]);
}

bool SyncAccount()
{
   string response = "";
   string payload = BuildSyncPayload();
   return HttpRequest("POST", "/api/mt4/bridge/sync", payload, response);
}

// Read-only connector: this build contains no order-placement or command-polling code.

int OnInit()
{
   if(BridgeToken == "" || ExpectedAccountLogin <= 0 || ExpectedServer == "")
   {
      Print("QUANTUM AI: Set BridgeToken, ExpectedAccountLogin and ExpectedServer in EA inputs.");
      return INIT_PARAMETERS_INCORRECT;
   }
   if(!AccountIsExpected())
   {
      Print("QUANTUM AI: Refusing connection. This EA requires the registered JustMarkets DEMO account.");
      return INIT_FAILED;
   }
   for(int i=0; i<ArraySize(Symbols); i++) SymbolSelect(Symbols[i], true);
   EventSetTimer(MathMax(2, SyncIntervalSeconds));
   Print("QUANTUM AI JustMarkets MT4 read-only demo bridge connected. No order placement is included.");
   SyncAccount();
   SyncAllMarketCandles();
   lastCandleSync = TimeCurrent();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   if(!AccountIsExpected()) return;
   SyncAccount();
   if(TimeCurrent() - lastCandleSync >= MathMax(10, CandleSyncIntervalSeconds))
   {
      SyncAllMarketCandles();
      lastCandleSync = TimeCurrent();
   }
}

void OnTick()
{
   // Timer-driven bridge: no order is opened from a chart tick.
}
