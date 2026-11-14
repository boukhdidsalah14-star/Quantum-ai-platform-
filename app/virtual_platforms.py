"""Customer-isolated virtual trading accounts. No broker orders are sent."""
import os, time, secrets, math
from app.database import sqlite3
from pathlib import Path

PLATFORMS={"binary":{"name":"Olymp-style Binary","initial":63578.0},
"forex":{"name":"MetaTrader-style Forex","initial":13790.0},
"crypto":{"name":"Binance-style Crypto","initial":78578.0}}

def dbopen():
 p=Path(os.getenv("QUANTUM_DB_PATH","data/quantum_ai.sqlite3")); p.parent.mkdir(parents=True,exist_ok=True)
 d=sqlite3.connect(p,timeout=15); d.row_factory=sqlite3.Row; d.execute("PRAGMA foreign_keys=ON"); return d

def init_db():
 with dbopen() as d:
  d.execute("""CREATE TABLE IF NOT EXISTS virtual_accounts(customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,platform TEXT NOT NULL,starting_balance REAL NOT NULL,balance REAL NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,PRIMARY KEY(customer_id,platform))""")
  d.execute("""CREATE TABLE IF NOT EXISTS virtual_positions(id TEXT PRIMARY KEY,customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,platform TEXT NOT NULL,symbol TEXT NOT NULL,side TEXT NOT NULL,stake REAL NOT NULL,entry_price REAL NOT NULL,expiry_minutes INTEGER,payout_rate REAL NOT NULL DEFAULT .82,status TEXT NOT NULL,exit_price REAL,pnl REAL,result TEXT,idempotency_key TEXT NOT NULL,created_at INTEGER NOT NULL,settled_at INTEGER,UNIQUE(customer_id,platform,idempotency_key))""")
  d.execute("CREATE INDEX IF NOT EXISTS idx_virtual_positions ON virtual_positions(customer_id,platform,created_at)")

def ensure(customer):
 now=int(time.time())
 with dbopen() as d:
  for k,v in PLATFORMS.items(): d.execute("INSERT OR IGNORE INTO virtual_accounts VALUES(?,?,?,?,?,?)",(customer,k,v["initial"],v["initial"],now,now))

def snapshot(customer):
 ensure(customer); out={}; now=int(time.time())-86400
 with dbopen() as d:
  for a in d.execute("SELECT * FROM virtual_accounts WHERE customer_id=?",(customer,)).fetchall():
   s=d.execute("""SELECT COALESCE(SUM(CASE WHEN status='settled' AND pnl<0 AND settled_at>=? THEN -pnl ELSE 0 END),0) loss,COALESCE(SUM(CASE WHEN status='open' THEN stake ELSE 0 END),0) reserved,SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) n FROM virtual_positions WHERE customer_id=? AND platform=?""",(now,customer,a["platform"])).fetchone()
   cap=round(a["starting_balance"]*.10,2); loss=round(s["loss"],2); reserved=round(s["reserved"],2)
   out[a["platform"]]={"name":PLATFORMS[a["platform"]]["name"],"balance":round(a["balance"],2),"starting_balance":a["starting_balance"],"daily_loss_limit":cap,"daily_loss":loss,"remaining_loss_allowance":round(max(0,cap-loss-reserved),2),"open_positions":int(s["n"] or 0),"account_type":"VIRTUAL SIMULATION"}
 return out

def positions(customer,platform):
 if platform not in PLATFORMS: raise ValueError("Unknown virtual platform")
 ensure(customer)
 with dbopen() as d:return [dict(x) for x in d.execute("SELECT * FROM virtual_positions WHERE customer_id=? AND platform=? ORDER BY created_at DESC LIMIT 100",(customer,platform)).fetchall()]

def open_position(customer,platform,symbol,side,stake,price,expiry,key):
 if platform not in PLATFORMS: raise ValueError("Unknown virtual platform")
 symbol=str(symbol).strip().upper(); side=str(side).strip().upper(); stake=float(stake); price=float(price)
 allowed={"CALL","PUT"} if platform=="binary" else {"BUY","SELL"}
 if not symbol or len(symbol)>30 or side not in allowed: raise ValueError("Invalid symbol or direction")
 if not math.isfinite(stake) or stake<=0 or not math.isfinite(price) or price<=0: raise ValueError("Stake and entry price must be positive")
 if platform=="binary" and expiry not in {1,5,10,15,30,60}: raise ValueError("Invalid binary expiry")
 if platform!="binary": expiry=None
 if not key or len(key)>100: raise ValueError("Invalid order reference")
 ensure(customer); now=int(time.time())
 with dbopen() as d:
  old=d.execute("SELECT * FROM virtual_positions WHERE customer_id=? AND platform=? AND idempotency_key=?",(customer,platform,key)).fetchone()
  if old:return dict(old)
  a=d.execute("SELECT * FROM virtual_accounts WHERE customer_id=? AND platform=?",(customer,platform)).fetchone()
  s=d.execute("""SELECT COALESCE(SUM(CASE WHEN status='settled' AND pnl<0 AND settled_at>=? THEN -pnl ELSE 0 END),0) loss,COALESCE(SUM(CASE WHEN status='open' THEN stake ELSE 0 END),0) reserved,SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) n FROM virtual_positions WHERE customer_id=? AND platform=?""",(now-86400,customer,platform)).fetchone()
  if stake>a["balance"]: raise ValueError("Stake exceeds virtual account balance")
  if s["loss"]+s["reserved"]+stake>a["starting_balance"]*.10: raise ValueError("Trade exceeds the 10% daily loss allowance")
  if (s["n"] or 0)>=10: raise ValueError("Maximum 10 open positions per platform")
  pid=secrets.token_urlsafe(18)
  d.execute("INSERT INTO virtual_positions(id,customer_id,platform,symbol,side,stake,entry_price,expiry_minutes,status,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,'open',?,?)",(pid,customer,platform,symbol,side,stake,price,expiry,key,now))
  return dict(d.execute("SELECT * FROM virtual_positions WHERE id=?",(pid,)).fetchone())

def settle(customer,platform,pid,exit_price):
 exit_price=float(exit_price)
 if not math.isfinite(exit_price) or exit_price<=0: raise ValueError("Exit price must be positive")
 now=int(time.time())
 with dbopen() as d:
  r=d.execute("SELECT * FROM virtual_positions WHERE id=? AND customer_id=? AND platform=? AND status='open'",(pid,customer,platform)).fetchone()
  if not r:return None
  if platform=="binary":
   if now<r["created_at"]+r["expiry_minutes"]*60: raise ValueError("Binary position has not expired")
   won=(exit_price>r["entry_price"] and r["side"]=="CALL") or (exit_price<r["entry_price"] and r["side"]=="PUT")
   result,pnl=("draw",0.0) if exit_price==r["entry_price"] else (("win",r["stake"]*r["payout_rate"]) if won else ("loss",-r["stake"]))
  else:
   pnl=r["stake"]*((exit_price-r["entry_price"])/r["entry_price"])*(1 if r["side"]=="BUY" else -1)
   result="win" if pnl>0 else "loss" if pnl<0 else "draw"
  d.execute("UPDATE virtual_positions SET status='settled',exit_price=?,pnl=?,result=?,settled_at=? WHERE id=? AND status='open'",(exit_price,pnl,result,now,pid))
  d.execute("UPDATE virtual_accounts SET balance=balance+?,updated_at=? WHERE customer_id=? AND platform=?",(pnl,now,customer,platform))
  return dict(d.execute("SELECT * FROM virtual_positions WHERE id=?",(pid,)).fetchone())
