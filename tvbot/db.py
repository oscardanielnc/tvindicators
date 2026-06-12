"""SQLite (WAL) - registro auditable de trades, senales, equity y eventos."""
import json
import sqlite3
import threading
from datetime import datetime

import config

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    tf TEXT NOT NULL,
    side TEXT NOT NULL,                -- long | short
    status TEXT NOT NULL,              -- open | closed
    t_signal TEXT NOT NULL,            -- cierre de vela que dio la senal (UTC ISO)
    t_entry TEXT NOT NULL,
    t_exit TEXT,
    entry_px REAL NOT NULL,
    exit_px REAL,
    base_amount REAL NOT NULL,         -- margen USD
    leverage REAL NOT NULL,
    notional REAL NOT NULL,
    qty REAL NOT NULL,
    stop_px REAL,
    timeout_at TEXT,
    exit_reason TEXT,                  -- SL | timeout | flip | manual | error
    pnl_usd REAL,                      -- neto (fees+funding incluidos)
    fees_usd REAL,
    funding_usd REAL,
    ret_pct_lev REAL,                  -- % sobre margen (con apalancamiento)
    ret_pct_nolev REAL,                -- % movimiento neto sin apalancamiento
    atr_entry REAL,
    bars_held INTEGER,
    signal_meta TEXT                   -- JSON extra
);
CREATE INDEX IF NOT EXISTS ix_trades_strat ON trades(strategy_id, status);
CREATE INDEX IF NOT EXISTS ix_trades_status ON trades(status);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    ts TEXT PRIMARY KEY,
    equity REAL NOT NULL,              -- realizado + no realizado
    realized REAL NOT NULL,
    unrealized REAL NOT NULL,
    open_positions INTEGER NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    kind TEXT NOT NULL,                -- entry | entry_skipped | exit
    detail TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,               -- info | warn | error
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    detail TEXT
);
"""


def utcnow():
    """Hora actual de Lima, Peru (nombre conservado por compatibilidad interna)."""
    return datetime.now(config.LIMA_TZ).isoformat(timespec="seconds")


def conn():
    c = sqlite3.connect(config.DB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, conn() as c:
        c.executescript(SCHEMA)


def insert_trade(**kw):
    cols = ",".join(kw)
    q = f"INSERT INTO trades ({cols}) VALUES ({','.join('?' * len(kw))})"
    with _lock, conn() as c:
        cur = c.execute(q, list(kw.values()))
        return cur.lastrowid


def close_trade(trade_id, **kw):
    sets = ",".join(f"{k}=?" for k in kw)
    with _lock, conn() as c:
        c.execute(f"UPDATE trades SET status='closed', {sets} WHERE id=?",
                  list(kw.values()) + [trade_id])


def open_trades():
    with _lock, conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM trades WHERE status='open'")]


def realized_pnl():
    with _lock, conn() as c:
        r = c.execute("SELECT COALESCE(SUM(pnl_usd),0) s FROM trades WHERE status='closed'").fetchone()
        return r["s"]


def snapshot_equity(equity, realized, unrealized, n_open, detail=None):
    with _lock, conn() as c:
        c.execute("INSERT OR REPLACE INTO equity_snapshots VALUES (?,?,?,?,?,?)",
                  (utcnow(), equity, realized, unrealized, n_open,
                   json.dumps(detail) if detail else None))


def log_signal(strategy_id, symbol, kind, detail=None):
    with _lock, conn() as c:
        c.execute("INSERT INTO signals (ts,strategy_id,symbol,kind,detail) VALUES (?,?,?,?,?)",
                  (utcnow(), strategy_id, symbol, kind, json.dumps(detail) if detail else None))


def log_event(level, category, message, detail=None):
    with _lock, conn() as c:
        c.execute("INSERT INTO events (ts,level,category,message,detail) VALUES (?,?,?,?,?)",
                  (utcnow(), level, category, message, json.dumps(detail) if detail else None))
