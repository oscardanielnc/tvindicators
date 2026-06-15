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
from tvbot.strategies import STRATEGIES, BACKTEST_REF

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
                    "exit_desc": s.exit_desc, "indicators": s.indicators, "note": s.note,
                    "role": s.role, "open_now": n_open, **{k: r.get(k) for k in
                    ("n_trades", "wins", "pnl_total", "avg_ret_lev", "avg_ret_nolev")}})
    return out


def _eval_rows(gate=None):
    gate = gate or config.GATE_MIN_TRADES
    out = []
    for s in STRATEGIES:
        rows = q("SELECT ret_pct_nolev, pnl_usd, mae_r, mfe_r FROM trades WHERE strategy_id=? "
                 "AND status='closed' AND ret_pct_nolev IS NOT NULL", (s.sid,))
        rets = [r["ret_pct_nolev"] for r in rows]
        n = len(rets)
        wins = [x for x in rets if x > 0]
        losses = [x for x in rets if x <= 0]
        pnl = round(sum((r["pnl_usd"] or 0) for r in rows), 2)
        wr = round(len(wins) / n * 100) if n else None
        live_exp = round(sum(rets) / n * 100, 1) if n else None      # bps de nominal
        sl = sum(losses)
        pf = (round(sum(wins) / abs(sl), 2) if sl < 0 else (99.9 if wins else None))
        maes = [r["mae_r"] for r in rows if r["mae_r"] is not None]
        mfes = [r["mfe_r"] for r in rows if r["mfe_r"] is not None]
        bt_exp, bt_pf = BACKTEST_REF.get(s.sid, (None, None))
        ratio = round(live_exp / bt_exp, 2) if (live_exp is not None and bt_exp) else None
        # gate de producción (config): nº trades + exp>0 + ratio + PF
        gate_pass = bool(n >= config.GATE_MIN_TRADES and live_exp and live_exp > 0
                         and ratio is not None and ratio >= config.GATE_MIN_RATIO
                         and pf is not None and pf >= config.GATE_MIN_PF)
        if n == 0:
            vc, vl = "none", "Sin datos"
        elif n < 10:
            vc, vl = "collect", "Recolectando"
        elif n < gate:
            vc, vl = ("ok", "En línea") if live_exp > 0 else ("watch", "Vigilar")
        elif gate_pass:
            vc, vl = "pass", "Confirmada ✓ (a producción)"
        else:
            vc, vl = ("watch", "Vigilar") if (live_exp or 0) > 0 else ("fail", "Candidata a quitar")
        out.append({
            "strategy_id": s.sid, "name": s.name, "coin": s.coin, "tf": s.tf,
            "side": "long" if s.side > 0 else "short",
            "role": "titular" if s.role == 1 else "suplente", "note": s.note,
            "n": n, "wr": wr, "live_exp": live_exp, "pf": pf, "pnl": pnl,
            "bt_exp": bt_exp, "bt_pf": bt_pf, "ratio": ratio, "gate_pass": gate_pass,
            "avg_mae_r": round(sum(maes) / len(maes), 2) if maes else None,
            "avg_mfe_r": round(sum(mfes) / len(mfes), 2) if mfes else None,
            "verdict": vc, "verdict_label": vl,
        })
    return out


@app.get("/api/evaluation")
def evaluation(gate: int = None):
    """Desempeno LIVE por estrategia vs backtest + veredicto + gate de producción."""
    return {"gate": gate or config.GATE_MIN_TRADES, "rows": _eval_rows(gate)}


@app.get("/api/portfolio")
def portfolio():
    """Tracker de confirmación a NIVEL CARTERA: el track vivo agregado vs el backtest.
    Es la señal de go-live del lote 1 (porque las estrategias de baja frecuencia tardan años
    individualmente, pero el libro junta potencia estadística rápido)."""
    rows = _eval_rows()
    traded = [r for r in rows if r["n"] > 0]
    confirmed = [r for r in rows if r["gate_pass"]]
    # agregados de trades cerrados
    tr = q("SELECT ret_pct_nolev, pnl_usd, mae_r, mfe_r FROM trades "
           "WHERE status='closed' AND ret_pct_nolev IS NOT NULL")
    rets = [t["ret_pct_nolev"] for t in tr]
    n = len(rets)
    wins = sum(1 for x in rets if x > 0)
    live_exp = round(sum(rets) / n * 100, 1) if n else None          # bps de nominal
    bt_exps = [r["bt_exp"] for r in rows if r["n"] > 0 and r["bt_exp"]]
    bt_exp_avg = round(sum(bt_exps) / len(bt_exps), 1) if bt_exps else None
    maes = [t["mae_r"] for t in tr if t["mae_r"] is not None]
    mfes = [t["mfe_r"] for t in tr if t["mfe_r"] is not None]
    # curva de equity -> maxDD vivo
    eq = q("SELECT equity FROM equity_snapshots ORDER BY ts")
    dd = 0.0
    if eq:
        peak = eq[0]["equity"]
        for e in eq:
            peak = max(peak, e["equity"])
            dd = min(dd, e["equity"] / peak - 1) if peak else dd
    # veredicto de cartera
    if n < config.GATE_PORT_MIN_TRADES:
        vc, vl = "collect", f"Acumulando ({n}/{config.GATE_PORT_MIN_TRADES} trades)"
    elif (live_exp or 0) <= 0:
        vc, vl = "fail", "Alerta: el vivo NO confirma el backtest"
    elif len(confirmed) >= config.GATE_PORT_MIN_CONFIRMED:
        vc, vl = "pass", "Listo para lote 1 a producción ✓"
    else:
        vc, vl = "ok", f"En progreso ({len(confirmed)}/{config.GATE_PORT_MIN_CONFIRMED} confirmadas)"
    return {
        "n_trades": n, "wr": round(wins / n * 100) if n else None,
        "live_exp": live_exp, "bt_exp_avg": bt_exp_avg,
        "ratio": round(live_exp / bt_exp_avg, 2) if (live_exp and bt_exp_avg) else None,
        "live_maxdd_pct": round(dd * 100, 2),
        "strategies_traded": len(traded), "strategies_confirmed": len(confirmed),
        "confirmed_ids": [r["strategy_id"] for r in confirmed],
        "avg_mae_r": round(sum(maes) / len(maes), 2) if maes else None,
        "avg_mfe_r": round(sum(mfes) / len(mfes), 2) if mfes else None,
        "gate": {"trades": config.GATE_PORT_MIN_TRADES, "confirmed": config.GATE_PORT_MIN_CONFIRMED,
                 "strat_trades": config.GATE_MIN_TRADES, "strat_ratio": config.GATE_MIN_RATIO,
                 "strat_pf": config.GATE_MIN_PF},
        "verdict": vc, "verdict_label": vl,
    }


@app.get("/api/evaluation.csv", response_class=PlainTextResponse)
def evaluation_csv(gate: int = 30, download: bool = True):
    """Resumen de evaluacion en CSV (descargable) para analisis offline."""
    rows = evaluation(gate)["rows"]
    cols = ["strategy_id", "role", "coin", "side", "tf", "n", "wr", "live_exp",
            "bt_exp", "ratio", "pf", "bt_pf", "pnl", "verdict_label"]
    lines = [",".join(cols)]
    for r in rows:
        lines.append(",".join("" if r.get(c) is None else str(r.get(c)) for c in cols))
    headers = {}
    if download:
        headers["Content-Disposition"] = 'attachment; filename="tvbot_evaluacion.csv"'
    return PlainTextResponse("\n".join(lines), headers=headers)


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
