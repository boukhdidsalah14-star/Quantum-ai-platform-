//+------------------------------------------------------------------+
//| QUANTUM AI - JustMarkets MT4 bridge (demo-first)                 |
//| Install in MT4: MQL4/Experts/ and compile with MetaEditor.        |
//| This EA refuses live accounts. It syncs positions and quotes;    |
//| demo orders require both EA input and server-side demo switches. |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "Customer-isolated QUANTUM AI JustMarkets MT4 bridge"

input string ApiBaseUrl = "https://quantum-ai-iqoption-preview.onrender.com";
input string BridgeToken = "";
input int ExpectedAccountLogin = 0;
input string ExpectedServer = "";
input int SyncIntervalSeconds = 5;
input bool EnableDemoOrderExecution = false;
input int MagicNumber = 914110;
input int SlippagePoints = 30;

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

bool SyncAccount()
{
   string response = "";
   string payload = BuildSyncPayload();
   return HttpRequest("POST", "/api/mt4/bridge/sync", payload, response);
}

void SendCommandResult(string commandId, string status, int ticket, string message)
{
   string body = "{";
   body += "\"account_login\":\"" + IntegerToString(AccountNumber()) + "\",";
   body += "\"account_server\":\"" + JsonEscape(AccountServer()) + "\",";
   body += "\"company\":\"" + JsonEscape(AccountCompany()) + "\",";
   body += "\"command_id\":\"" + JsonEscape(commandId) + "\",";
   body += "\"status\":\"" + status + "\",";
   body += "\"ticket\":" + IntegerToString(ticket) + ",";
   body += "\"message\":\"" + JsonEscape(message) + "\"";
   body += "}";
   string response = "";
   HttpRequest("POST", "/api/mt4/bridge/command-result", body, response);
}

int FindExistingCommand(string commandComment)
{
   for(int i=0; i<OrdersTotal(); i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() == MagicNumber && OrderComment() == commandComment)
         return OrderTicket();
   }
   for(int j=0; j<OrdersHistoryTotal(); j++)
   {
      if(!OrderSelect(j, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderMagicNumber() == MagicNumber && OrderComment() == commandComment)
         return OrderTicket();
   }
   return -1;
}

void ProcessCommand(string line)
{
   string fields[];
   int n = StringSplit(line, StringGetCharacter("|", 0), fields);
   if(n != 6) return;
   string commandId = fields[0];
   string symbol = fields[1];
   string side = fields[2];
   double lots = StrToDouble(fields[3]);
   double sl = StrToDouble(fields[4]);
   double tp = StrToDouble(fields[5]);
   string comment = "QAI:" + commandId;

   int existingTicket = FindExistingCommand(comment);
   if(existingTicket > 0)
   {
      SendCommandResult(commandId, "executed", existingTicket, "Duplicate delivery; existing MT4 order found.");
      return;
   }
   if(!EnableDemoOrderExecution || !AccountIsExpected())
   {
      SendCommandResult(commandId, "failed", 0, "EA demo execution is disabled or account verification failed.");
      return;
   }
   if(!IsAllowedSymbol(symbol) || (side != "BUY" && side != "SELL"))
   {
      SendCommandResult(commandId, "failed", 0, "Unsupported symbol or order side.");
      return;
   }
   if(lots < 0.01 || lots > 0.10)
   {
      SendCommandResult(commandId, "failed", 0, "Lot size is outside the demo safety limit.");
      return;
   }
   if(MarketInfo(symbol, MODE_TRADEALLOWED) == 0)
   {
      SendCommandResult(commandId, "failed", 0, "Symbol is not enabled for trading in this MT4 terminal.");
      return;
   }

   RefreshRates();
   int digits = (int)MarketInfo(symbol, MODE_DIGITS);
   double point = MarketInfo(symbol, MODE_POINT);
   double stopDistance = MarketInfo(symbol, MODE_STOPLEVEL) * point;
   double price = (side == "BUY" ? MarketInfo(symbol, MODE_ASK) : MarketInfo(symbol, MODE_BID));
   sl = NormalizeDouble(sl, digits);
   tp = NormalizeDouble(tp, digits);
   if(price <= 0 || point <= 0)
   {
      SendCommandResult(commandId, "failed", 0, "No current broker quote for symbol.");
      return;
   }
   if(side == "BUY" && !(sl < price && tp > price && price-sl >= stopDistance && tp-price >= stopDistance))
   {
      SendCommandResult(commandId, "failed", 0, "BUY stop-loss/take-profit is invalid for the current broker quote.");
      return;
   }
   if(side == "SELL" && !(tp < price && sl > price && sl-price >= stopDistance && price-tp >= stopDistance))
   {
      SendCommandResult(commandId, "failed", 0, "SELL stop-loss/take-profit is invalid for the current broker quote.");
      return;
   }

   int orderType = (side == "BUY" ? OP_BUY : OP_SELL);
   ResetLastError();
   int ticket = OrderSend(symbol, orderType, lots, NormalizeDouble(price, digits),
                          SlippagePoints, sl, tp, comment, MagicNumber, 0,
                          (side == "BUY" ? clrLime : clrTomato));
   if(ticket < 0)
   {
      int errorCode = GetLastError();
      SendCommandResult(commandId, "failed", 0, "OrderSend failed with MT4 error " + IntegerToString(errorCode));
      return;
   }
   SendCommandResult(commandId, "executed", ticket, "JustMarkets MT4 demo order opened.");
}

void PollCommands()
{
   if(!EnableDemoOrderExecution || !AccountIsExpected()) return;
   string path = "/api/mt4/bridge/commands?account_login=" + IntegerToString(AccountNumber()) +
                 "&account_server=" + UrlEncode(AccountServer()) +
                 "&company=" + UrlEncode(AccountCompany());
   string response = "";
   if(!HttpRequest("GET", path, "", response)) return;
   string lines[];
   int count = StringSplit(response, StringGetCharacter("\n", 0), lines);
   for(int i=0; i<count; i++)
   {
      string line = StringTrimLeft(lines[i]);
      line = StringTrimRight(line);
      if(line != "") ProcessCommand(line);
   }
}

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
   Print("QUANTUM AI JustMarkets MT4 bridge connected in read-only demo sync mode.");
   SyncAccount();
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
   PollCommands();
}

void OnTick()
{
   // Timer-driven bridge: no order is opened from a chart tick.
}
