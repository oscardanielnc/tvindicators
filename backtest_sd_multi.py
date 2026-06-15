"""Tests adicionales (pedido del usuario, 14/06/2026):
  1. Entrada SELECTIVA (event + cooldown, pocos trades/dia): ¿la selectividad rescata el edge?
  2. SL mas cercano: la columna exp ya barre TODOS los SL -> si el mejor es negativo, ningun SL ayuda.
  3. Multi-TF (1m/5m/15m/1h): ¿una TF mayor da edge? (13bps de costo = fraccion menor del movimiento)
Exits en multiplos de ATR (auto-escala entre TFs). ret_pess = conservador. Veredicto por celda.
Uso: python backtest_sd_multi.py
"""
import sys
import numpy as np
import pandas as pd

import sd_replica as R
from tvbot import indicators as I

sys.stdout.reconfigure(encoding="utf-8")

IS_OOS_CUT = pd.Timestamp("2026-01-01", tz="UTC")
RT_BPS = 13.0
TP_ATR = [1.0, 1.5, 2.0, 3.0]
SL_ATR = [0.5, 1.0, 1.5, 2.0, 3.0]
TIMEOUT = {"1m": 240, "5m": 200, "15m": 160, "1h": 72}
COOLDOWN = {"1m": 240, "5m": 48, "15m": 16, "1h": 4}   # ~4h de espera tras cada salida (≈ selectividad del canal)

OUT = []
def p(s=""):
    print(s, flush=True)
    OUT.append(s)


def split(tr):
    return tr[tr.t_in < IS_OOS_CUT], tr[tr.t_in >= IS_OOS_CUT]


def cell(coin, tf):
    try:
        df = R.load(coin, tf)
    except Exception as e:
        p(f"| {coin} | {tf} | — | SIN DATOS ({str(e)[:30]}) | | | | | | |")
        return
    longs, shorts, _ = R.entries(df, 50, 10, event=True)
    atr = I.atr14(df).values
    days = max((df.index[-1] - df.index[0]).days, 1)
    best = None
    tight = None     # SL mas cercano (0.5 ATR), mejor TP
    for kt in TP_ATR:
        for ks in SL_ATR:
            trd = R.backtest(df, longs, shorts, atr=atr, tp_atr=kt, sl_atr=ks,
                             timeout=TIMEOUT[tf], cooldown=COOLDOWN[tf])
            m = R.metrics(trd, "ret_pess")
            if not m:
                continue
            if best is None or m["exp_bps"] > best[-1]["exp_bps"]:
                best = (kt, ks, trd, m)
            if ks == SL_ATR[0] and (tight is None or m["exp_bps"] > tight[-1]["exp_bps"]):
                tight = (kt, ks, trd, m)
    if not best:
        p(f"| {coin} | {tf} | 0 | sin trades | | | | | | |")
        return
    kt, ks, trd, m = best
    mi, mo = R.metrics(split(trd)[0]), R.metrics(split(trd)[1])
    tpd = m["n"] / days
    gross = m["exp_bps"] + RT_BPS
    oos_pos = bool(mo and mo["exp_bps"] > 0 and mi and mi["exp_bps"] > 0)
    verd = "⚠ REVISAR" if oos_pos else "sin edge"
    is_e = f"{mi['exp_bps']:+.0f}" if mi else "—"
    oo_e = f"{mo['exp_bps']:+.0f}" if mo else "—"
    tm = tight[-1]
    p(f"| {coin} | {tf} | {tpd:.1f} | TP{kt}/SL{ks}×ATR | {m['wr']*100:.0f}% | "
      f"{m['exp_bps']:+.1f} | {gross:+.1f} | {m['pf']:.2f} | {is_e}/{oo_e} | "
      f"{m['worst5_bps'][0]:+.0f} | SLcerca exp={tm['exp_bps']:+.0f} peor={tm['worst5_bps'][0]:+.0f} | {verd} |")


p("# Tests adicionales: selectividad · SL cercano · multi-TF\n")
p(f"Entrada event+cooldown · exits ATR · costos {RT_BPS}bps RT · ret_pess (conservador) · IS<2026 / OOS 2026")
p("_gross_bps = exp + costo (el edge BRUTO antes de comisiones; si ~0, la entrada no predice nada)._\n")
p("| coin | TF | tr/día | mejor cfg | WR | exp_bps | gross_bps | PF | IS/OOS | peor1 | SL más cercano | veredicto |")
p("|---|---|---|---|---|---|---|---|---|---|---|---|")
for coin in ["BTC", "ETH"]:
    for tf in ["1m", "5m", "15m", "1h"]:
        cell(coin, tf)
with open("backtest_sd_multi.md", "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
p("\n→ backtest_sd_multi.md")
