"""QUANTUM AI invite-and-earn referral rewards."""
from __future__ import annotations
import os, secrets, string, time
from pathlib import Path
from app.database import sqlite3

def _connect():
    path=Path(os.getenv("QUANTUM_DB_PATH","data/quantum_ai.sqlite3"))
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(str(path),timeout=15)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS referral_codes(
          customer_id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS referral_attributions(
          referred_customer_id TEXT PRIMARY KEY, referrer_customer_id TEXT NOT NULL,
          created_at INTEGER NOT NULL, paid_at INTEGER, paid_order_id TEXT UNIQUE
        );
        CREATE INDEX IF NOT EXISTS idx_referral_owner ON referral_attributions(referrer_customer_id);
        CREATE TABLE IF NOT EXISTS referral_rewards(
          id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_customer_id TEXT NOT NULL,
          registered_snapshot INTEGER NOT NULL, paid_snapshot INTEGER NOT NULL,
          granted_at INTEGER NOT NULL, days INTEGER NOT NULL DEFAULT 30
        );
        CREATE INDEX IF NOT EXISTS idx_referral_rewards_owner ON referral_rewards(referrer_customer_id);
        """)

def _ensure_code(db, customer_id):
    row=db.execute("SELECT code FROM referral_codes WHERE customer_id=?",(customer_id,)).fetchone()
    if row: return row["code"]
    alphabet=string.ascii_uppercase+string.digits
    for _ in range(8):
        code="QAI"+''.join(secrets.choice(alphabet) for _ in range(7))
        try:
            db.execute("INSERT INTO referral_codes(customer_id,code,created_at) VALUES(?,?,?)",(customer_id,code,int(time.time())))
            return code
        except sqlite3.IntegrityError:
            continue
    raise RuntimeError("Could not allocate a referral code")

def attach_signup(referred_customer_id, code):
    init_db()
    code=(code or "").strip().upper()
    if not code: return False
    with _connect() as db:
        owner=db.execute("SELECT customer_id FROM referral_codes WHERE code=?",(code,)).fetchone()
        if not owner or owner["customer_id"]==referred_customer_id: return False
        try:
            db.execute("INSERT INTO referral_attributions(referred_customer_id,referrer_customer_id,created_at) VALUES(?,?,?)",
                       (referred_customer_id,owner["customer_id"],int(time.time())))
            return True
        except sqlite3.IntegrityError:
            return False

def _grant_qualified_rewards(db, owner_id):
    totals=db.execute("SELECT COUNT(*) AS registrations, COUNT(paid_at) AS paid FROM referral_attributions WHERE referrer_customer_id=?",(owner_id,)).fetchone()
    latest=db.execute("SELECT registered_snapshot,paid_snapshot FROM referral_rewards WHERE referrer_customer_id=? ORDER BY id DESC LIMIT 1",(owner_id,)).fetchone()
    reg_base=int(latest["registered_snapshot"]) if latest else 0
    paid_base=int(latest["paid_snapshot"]) if latest else 0
    if int(totals["registrations"])-reg_base < 8 or int(totals["paid"])-paid_base < 2:
        return False
    now=int(time.time())
    sub=db.execute("SELECT starts_at,expires_at FROM customer_subscriptions WHERE customer_id=?",(owner_id,)).fetchone()
    starts=max(now,int(sub["expires_at"])) if sub else now
    expires=starts+30*86400
    db.execute("""INSERT INTO customer_subscriptions(customer_id,status,starts_at,expires_at,last_order_id,updated_at)
      VALUES(?,'active',?,?,?,?) ON CONFLICT(customer_id) DO UPDATE SET status='active',
      starts_at=excluded.starts_at,expires_at=excluded.expires_at,last_order_id=excluded.last_order_id,updated_at=excluded.updated_at""",
      (owner_id,starts,expires,"referral_"+secrets.token_hex(8),now))
    db.execute("INSERT INTO referral_rewards(referrer_customer_id,registered_snapshot,paid_snapshot,granted_at,days) VALUES(?,?,?,?,30)",
               (owner_id,int(totals["registrations"]),int(totals["paid"]),now))
    return True

def record_paid_customer(referred_customer_id, order_id):
    init_db()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT referrer_customer_id,paid_at FROM referral_attributions WHERE referred_customer_id=?",(referred_customer_id,)).fetchone()
        if not row or row["paid_at"] is not None: return False
        db.execute("UPDATE referral_attributions SET paid_at=?,paid_order_id=? WHERE referred_customer_id=? AND paid_at IS NULL",
                   (int(time.time()),str(order_id),referred_customer_id))
        return _grant_qualified_rewards(db,row["referrer_customer_id"])

def dashboard(customer_id, base_url):
    init_db()
    with _connect() as db:
        code=_ensure_code(db,customer_id)
        counts=db.execute("SELECT COUNT(*) AS registrations,COUNT(paid_at) AS paid FROM referral_attributions WHERE referrer_customer_id=?",(customer_id,)).fetchone()
        reward=db.execute("SELECT registered_snapshot,paid_snapshot,granted_at FROM referral_rewards WHERE referrer_customer_id=? ORDER BY id DESC LIMIT 1",(customer_id,)).fetchone()
        reg=int(counts["registrations"]); paid=int(counts["paid"])
        reg_base=int(reward["registered_snapshot"]) if reward else 0
        paid_base=int(reward["paid_snapshot"]) if reward else 0
        history=db.execute("SELECT days,granted_at FROM referral_rewards WHERE referrer_customer_id=? ORDER BY id DESC LIMIT 10",(customer_id,)).fetchall()
    return {"code":code,"link":base_url.rstrip("/")+"/?ref="+code,"signups":reg,"paid_referrals":paid,
      "signups_to_next_reward":max(0,8-(reg-reg_base)),"paid_to_next_reward":max(0,2-(paid-paid_base)),
      "reward_eligible":reg-reg_base>=8 and paid-paid_base>=2,
      "rewards":[{"days":r["days"],"granted_at":r["granted_at"]} for r in history],
      "rules":{"signups":8,"paid":2,"reward_days":30}}
