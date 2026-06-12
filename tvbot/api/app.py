"""API REST para el dashboard (pantalla 1: resumen; pantalla 2: historico por estrategia).
Todas las horas en zona de Lima, Peru (UTC-5)."""
import json
import re
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

import config
from tvbot.strategies import STRATEGIES

app = FastAPI(title="tvbot", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC = Path(__file__).parent / "static"


@app.get("/")
def dashboard():
    return FileResponse(STATIC / "dashboard.html")


def q(sql, args=()):
    c = sqlite3.connect(config.DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


@app.get("/api/health")
def health():
    ev = q("SELECT ts, level, message FROM events ORDER BY id DESC LIMIT 1")
    eq = q("SELECT ts FROM equity_snapshots ORDER BY ts DESC LIMIT 1")
    return {"ok": True, "last_event": ev[0] if ev else None,
            "last_snapshot": eq[0]["ts"] if eq else None}


@app.get("/api/status")
def status():
    eq = q("SELECT * FROM equity_snapshots ORDER BY ts DESC LIMIT 1")
    open_tr = q("SELECT * FROM trades WHERE status='open'")
    closed = q("""SELECT COUNT(*) n, COALESCE(SUM(pnl_usd),0) pnl,
                  SUM(CASE WHEN pnl_usd>0 THEN 1 ELSE 0 END) wins
                  FROM trades WHERE status='closed'""")[0]
    return {
        "capital_inicial": config.CAPITAL_INICIAL,
        "leverage": config.LEVERAGE, "margin_pct": config.MARGIN_PCT,
        "equity": eq[0] if eq else None,
        "open_positions": open_tr,
        "closed_total": closed["n"],
        "wins": closed["wins"] or 0,
        "losses": (closed["n"] or 0) - (closed["wins"] or 0),
        "pnl_total": round(closed["pnl"], 2),
    }


@app.get("/api/equity")
def equity(limit: int = 2000):
    return q("SELECT ts, equity, realized, unrealized, open_positions "
             "FROM equity_snapshots ORDER BY ts DESC LIMIT ?", (limit,))[::-1]


@app.get("/api/summary")
def summary():
    """Para el grafico de barras: #trades y PnL por estrategia."""
    rows = q("""SELECT strategy_id, strategy_name,
                COUNT(*) n_trades,
                SUM(CASE WHEN pnl_usd>0 THEN 1 ELSE 0 END) wins,
                ROUND(COALESCE(SUM(pnl_usd),0),2) pnl_total,
                ROUND(AVG(ret_pct_lev),3) avg_ret_lev,
                ROUND(AVG(ret_pct_nolev),4) avg_ret_nolev
                FROM trades WHERE status='closed'
                GROUP BY strategy_id ORDER BY strategy_id""")
    by_id = {r["strategy_id"]: r for r in rows}
    out = []
    for s in STRATEGIES:
        r = by_id.get(s.sid, {"n_trades": 0, "wins": 0, "pnl_total": 0.0,
                              "avg_ret_lev": None, "avg_ret_nolev": None})
        n_open = q("SELECT COUNT(*) n FROM trades WHERE strategy_id=? AND status='open'",
                   (s.sid,))[0]["n"]
        out.append({"strategy_id": s.sid, "name": s.name, "coin": s.coin, "tf": s.tf,
                    "side": "long" if s.side > 0 else "short", "exit_mode": s.exit_mode,
                    "exit_desc": s.exit_desc, "indicators": s.indicators,
                    "role": s.role, "open_now": n_open, **{k: r.get(k) for k in
                    ("n_trades", "wins", "pnl_total", "avg_ret_lev", "avg_ret_nolev")}})
    return out


@app.get("/api/strategies")
def strategies():
    return [{"strategy_id": s.sid, "name": s.name, "coin": s.coin, "tf": s.tf,
             "side": "long" if s.side > 0 else "short", "exit_mode": s.exit_mode,
             "exit_desc": s.exit_desc, "indicators": s.indicators,
             "role": s.role} for s in STRATEGIES]


@app.get("/api/trades")
def trades(strategy_id: str = None, status: str = None, limit: int = 500):
    sql, args = "SELECT * FROM trades WHERE 1=1", []
    if strategy_id:
        sql += " AND strategy_id=?"; args.append(strategy_id)
    if status:
        sql += " AND status=?"; args.append(status)
    sql += " ORDER BY id DESC LIMIT ?"; args.append(limit)
    rows = q(sql, tuple(args))
    for r in rows:
        if r.get("signal_meta"):
            r["signal_meta"] = json.loads(r["signal_meta"])
    return rows


@app.get("/api/trades/{trade_id}")
def trade(trade_id: int):
    rows = q("SELECT * FROM trades WHERE id=?", (trade_id,))
    if not rows:
        raise HTTPException(404)
    return rows[0]


@app.get("/api/events")
def events(limit: int = 200, level: str = None, start: str = None, end: str = None):
    sql, args = "SELECT * FROM events WHERE 1=1", []
    if level:
        sql += " AND level=?"; args.append(level)
    if start:
        sql += " AND ts>=?"; args.append(start)
    if end:
        sql += " AND ts<=?"; args.append(end)
    sql += " ORDER BY id DESC LIMIT ?"; args.append(limit)
    return q(sql, tuple(args))


_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


@app.get("/api/logs", response_class=PlainTextResponse)
def logs(start: str = None, end: str = None, download: bool = False):
    """Logs del sistema filtrados por rango de fecha-hora de Lima.
    start/end formato 'YYYY-MM-DD' o 'YYYY-MM-DD HH:MM:SS'. download=true -> attachment."""
    start = (start or "0000-01-01").replace("T", " ")
    end = (end or "9999-12-31").replace("T", " ")
    if len(start) == 10: start += " 00:00:00"
    if len(end) == 10: end += " 23:59:59"
    files = sorted(config.LOG_DIR.glob("tvbot.log*"), reverse=True)  # rotaciones primero
    out, keep = [], False
    for f in files:
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                m = _TS_RE.match(line)
                if m:
                    keep = start <= m.group(1) <= end
                if keep:
                    out.append(line)
        except OSError:
            continue
    body = "\n".join(out) if out else f"(sin lineas de log entre {start} y {end})"
    headers = {}
    if download:
        fname = f"tvbot_logs_{start[:10]}_{end[:10]}.txt"
        headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return PlainTextResponse(body, headers=headers)
