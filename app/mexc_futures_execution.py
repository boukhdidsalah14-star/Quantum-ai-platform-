"""Signed MEXC USD-M perpetual futures execution helpers."""
from __future__ import annotations
import hashlib, hmac, json, time
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any
import httpx

BASE_URL="https://api.mexc.com"
ALLOWED_SYMBOLS={"BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","TRXUSDT","DOGEUSDT","ADAUSDT","BCHUSDT","LINKUSDT"}
MAX_ORDER_NOTIONAL_USDT=Decimal("500")
MAX_LEVERAGE=20

class MexcFuturesError(RuntimeError): pass

def _signature(api_key:str,api_secret:str,timestamp:str,request_param:str="")->str:
    return hmac.new(api_secret.encode(),(api_key+timestamp+request_param).encode(),hashlib.sha256).hexdigest()

def _headers(api_key:str,api_secret:str,timestamp:str|None=None,request_param:str="")->dict:
    ts=timestamp or str(int(time.time()*1000))
    return {"ApiKey":api_key,"Request-Time":ts,"Signature":_signature(api_key,api_secret,ts,request_param),
            "Content-Type":"application/json","Recv-Window":"5000","User-Agent":"QuantumAI/1.0"}

def _checked_payload(payload:Any)->Any:
    if not isinstance(payload,dict) or payload.get("success") is not True or payload.get("code") not in (0,"0"):
        msg=payload.get("message","MEXC Futures rejected the request") if isinstance(payload,dict) else "Invalid MEXC response"
        raise MexcFuturesError(str(msg)[:240])
    return payload.get("data")

def _parse_assets(payload:dict)->dict:
    rows=_checked_payload(payload)
    if not isinstance(rows,list): raise MexcFuturesError("Unexpected MEXC account response")
    assets=[]
    for row in rows:
        if isinstance(row,dict) and row.get("currency"):
            assets.append({"currency":str(row["currency"]).upper(),"available_balance":str(row.get("availableBalance","0")),
                "equity":str(row.get("equity","0")),"position_margin":str(row.get("positionMargin","0")),
                "unrealized_pnl":str(row.get("unrealized","0"))})
    return {"connected":True,"broker":"mexc","market":"usdt_margined_perpetual_futures","mode":"real","assets":assets}

def _contract_symbol(symbol:str)->str:
    s=symbol.upper().strip()
    if s not in ALLOWED_SYMBOLS: raise ValueError("Unsupported MEXC USD-M futures symbol")
    return s[:-4]+"_USDT"

def contracts_for_risk(*,symbol:str,entry_price:float,stop_loss:float,account_balance:float,
                       risk_percent:float,contract:dict,leverage:int,
                       max_notional:Decimal=MAX_ORDER_NOTIONAL_USDT)->dict:
    _contract_symbol(symbol)
    try:
        price,stop,balance,risk,size,step,minimum,maximum=map(Decimal,map(str,(
            entry_price,stop_loss,account_balance,risk_percent,contract["contractSize"],
            contract["volUnit"],contract["minVol"],contract["maxVol"])))
        lev=int(leverage)
    except (KeyError,TypeError,ValueError,InvalidOperation,OverflowError):
        raise ValueError("Valid contract and risk inputs are required")
    if not all(x.is_finite() and x>0 for x in (price,stop,balance,risk,size,step,minimum,maximum)):
        raise ValueError("Risk and contract values must be finite and positive")
    if isinstance(leverage,bool) or lev!=leverage or not 1<=lev<=MAX_LEVERAGE: raise ValueError("Leverage must be a whole number from 1x to 20x")
    if risk>1: raise ValueError("Risk cannot exceed 1% per trade")
    distance=abs(price-stop)
    if distance==0: raise ValueError("Stop-loss must differ from entry")
    budget=balance*risk/100
    base=min(budget/distance,max_notional/price)
    raw=base/size
    volume=(raw/step).to_integral_value(rounding=ROUND_DOWN)*step
    if volume<minimum: raise ValueError("Risk-sized order is below the contract minimum volume")
    volume=min(volume,(maximum/step).to_integral_value(rounding=ROUND_DOWN)*step)
    notional=volume*size*price
    if notional>max_notional: raise ValueError("Order exceeds configured notional cap")
    return {"symbol":symbol.upper(),"contracts":str(volume),"base_quantity":str(volume*size),
            "notional_usdt":str(notional),"risk_budget_usdt":str(budget),
            "estimated_stop_risk_usdt":str(volume*size*distance),
            "margin_estimate_usdt":str(notional/lev),"leverage":lev}

class MexcFuturesClient:
    def __init__(self,api_key:str,api_secret:str,timeout:float=12):
        if not api_key or len(api_key)>256 or not api_secret or len(api_secret)>512:
            raise ValueError("MEXC Futures API key and secret are required")
        self.api_key,self.api_secret,self.timeout=api_key,api_secret,timeout

    async def _request(self,method:str,path:str,params:dict|None=None,body:dict|None=None,signed:bool=True):
        method=method.upper(); params={k:v for k,v in (params or {}).items() if v is not None}
        if method in {"GET","DELETE"}:
            sign="&".join(f"{k}={v}" for k,v in sorted(params.items()))
            headers=_headers(self.api_key,self.api_secret,request_param=sign) if signed else {}
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout,connect=4)) as c:
                response=await c.request(method,BASE_URL+path,params=params,headers=headers)
        elif method=="POST":
            body_text=json.dumps(body or {},separators=(",",":"),ensure_ascii=False)
            headers=_headers(self.api_key,self.api_secret,request_param=body_text) if signed else {"Content-Type":"application/json"}
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout,connect=4)) as c:
                response=await c.post(BASE_URL+path,content=body_text.encode(),headers=headers)
        else: raise ValueError("Unsupported MEXC method")
        try:
            response.raise_for_status(); payload=response.json()
        except (httpx.HTTPError,ValueError) as exc:
            raise MexcFuturesError("MEXC Futures request failed; check API permissions and eligibility") from exc
        return _checked_payload(payload)

    async def verify_account(self)->dict:
        data=await self._request("GET","/api/v1/private/account/assets")
        return _parse_assets({"success":True,"code":0,"data":data})

    async def get_contract(self,symbol:str)->dict:
        contract_symbol=_contract_symbol(symbol)
        data=await self._request("GET","/api/v1/contract/detail/country",{"symbol":contract_symbol},signed=False)
        if isinstance(data,list): data=next((x for x in data if isinstance(x,dict) and x.get("symbol")==contract_symbol),None)
        if not isinstance(data,dict) or data.get("symbol")!=contract_symbol: raise MexcFuturesError("Contract metadata unavailable")
        if data.get("state")!=0 or data.get("apiAllowed") is not True or data.get("futureType")!=1: raise MexcFuturesError("Perpetual contract is not enabled for API trading")
        if str(data.get("quoteCoin","")).upper()!="USDT" or str(data.get("settleCoin","")).upper()!="USDT": raise MexcFuturesError("Only USDT-settled perpetuals are supported")
        return data

    async def get_open_positions(self,symbol:str|None=None)->list[dict]:
        params={"symbol":_contract_symbol(symbol)} if symbol else {}
        data=await self._request("GET","/api/v1/private/position/open_positions",params)
        if not isinstance(data,list): raise MexcFuturesError("Invalid open-position response")
        return [x for x in data if isinstance(x,dict) and int(x.get("state",0))==1]

    async def place_market_order(self,*,symbol:str,side:str,volume:str,leverage:int,stop_loss:float,
                                 take_profit:float,external_oid:str,position_mode:int=1)->dict:
        contract_symbol=_contract_symbol(symbol)
        side_value={"long":1,"short":3}.get(side.lower())
        if side_value is None: raise ValueError("Side must be long or short")
        if isinstance(leverage,bool) or not 1<=int(leverage)<=MAX_LEVERAGE: raise ValueError("Leverage must be from 1x to 20x")
        vol,sl,tp=Decimal(str(volume)),Decimal(str(stop_loss)),Decimal(str(take_profit))
        if not vol.is_finite() or vol<=0 or not sl.is_finite() or not tp.is_finite() or sl<=0 or tp<=0: raise ValueError("Invalid order volume or protection prices")
        if not external_oid or len(external_oid)>32: raise ValueError("Valid external order id required")
        body={"symbol":contract_symbol,"price":"0","vol":str(vol),"leverage":int(leverage),"side":side_value,
              "type":5,"openType":1,"externalOid":external_oid,"stopLossPrice":str(sl),"takeProfitPrice":str(tp),
              "lossTrend":1,"profitTrend":1,"positionMode":int(position_mode)}
        data=await self._request("POST","/api/v1/private/order/create",body=body)
        if not isinstance(data,dict) or not data.get("orderId"): raise MexcFuturesError("MEXC did not confirm order id")
        return {"order_id":str(data["orderId"]),"external_order_id":external_oid,"symbol":symbol.upper(),
                "side":side.lower(),"status":"submitted","stop_loss_attached":True,"take_profit_attached":True}

    async def close_position_market(self,position:dict,external_oid:str)->dict:
        symbol=str(position.get("symbol") or "")
        if symbol not in {_contract_symbol(s) for s in ALLOWED_SYMBOLS}: raise ValueError("Unsupported position symbol")
        ptype=int(position.get("positionType",0)); side=4 if ptype==1 else 2 if ptype==2 else 0
        volume=Decimal(str(position.get("holdVol","0")))
        if side==0 or volume<=0: raise ValueError("Invalid exchange position snapshot")
        body={"symbol":symbol,"price":"0","vol":str(volume),"side":side,"type":5,
              "openType":int(position.get("openType",1)),"positionId":int(position["positionId"]),
              "externalOid":external_oid,"positionMode":1}
        data=await self._request("POST","/api/v1/private/order/create",body=body)
        if not isinstance(data,dict) or not data.get("orderId"): raise MexcFuturesError("MEXC did not confirm close order id")
        return {"order_id":str(data["orderId"]),"status":"close_submitted","symbol":symbol,
                "position_id":str(position["positionId"])}

async def get_futures_account_info(api_key:str,api_secret:str)->dict:
    return await MexcFuturesClient(api_key,api_secret).verify_account()
