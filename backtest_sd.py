"""Backtest HONESTO de la replica S/D 1m (stream 'Forex Education Live').
Responde 3 preguntas:
  1. La entrada (momentum a favor de TREND), ¿tiene edge tras costos taker reales? (IS vs OOS)
  2. ¿Cual es el SL ideal? -> distribucion de MAE de las senales (el '1/5 vs 1/2' del usuario).
  3. ¿Es una aplanadora? -> los 5 peores trades y el comportamiento sin stop.
Banda intrabar: ret_pess (si una vela toca TP y SL asume SL) es la lectura CONSERVADORA.
Uso: python backtest_sd.py
"""
import sys
import numpy as np
import pandas as pd

import sd_replica as R

sys.stdout.reconfigure(encoding="utf-8")

IS_OOS_CUT = pd.Timestamp("2026-01-01", tz="UTC")
COINS = ["BTC", "ETH"]
ENTRY = dict(trend_len=50, entry_look=10)   # se fija tras validar frames (valida_sd.py)
TIMEOUT = 240
TP_GRID = [0.0010, 0.0015, 0.0020, 0.0030, 0.0050]
SL_GRID = [0.0010, 0.0020, 0.0030, 0.0050, 0.0100]

OUT = []
def p(s=""):
    print(s, flush=True)
    OUT.append(s)


def split(tr):
    return tr[tr.t_in < IS_OOS_CUT], tr[tr.t_in >= IS_OOS_CUT]


def mae_analysis(df, longs, shorts):
    p("\n### 2. MAE — ¿cuánto se va EN CONTRA antes de ir a favor? (el '1/5' del usuario)")
    p("```")
    p(f"{'fav_objetivo':>12} {'%senales_llegan':>16} {'MAE_med':>9} {'MAE_p75':>9} {'MAE_p90':>9}  (MAE = adverso antes de llegar, en %)")
    for fav in (0.0010, 0.0015, 0.0020, 0.0030):
        sm = R.signal_mae(df, longs, shorts, fav_thresh=fav, timeout=TIMEOUT)
        reached = sm[sm.reached_fav]
        pct = sm.reached_fav.mean() * 100
        if len(reached):
            med, p75, p90 = (reached.mae_before_fav.quantile(q) * 100 for q in (.5, .75, .9))
            p(f"{fav*100:11.2f}% {pct:15.1f}% {med:8.2f}% {p75:8.2f}% {p90:8.2f}%")
    p("```")
    p("_Lectura: si para capturar un TP de X%, el MAE_p90 es ~X/5, tu intuición se sostiene; "
      "si MAE_p90 >= X, el 'stop ideal' es mayor que el premio (mala geometría)._")


def sweep(df, longs, shorts, hi, lo):
    p("\n### 1+3. Barrido SL/TP (ret_pess, conservador) — edge + cola")
    p("```")
    p(f"{'TP%':>6}{'SL%':>6}{'n':>6}{'WR':>7}{'exp_bps':>9}{'PF':>6}{'tot%':>8}{'peor5_bps':>34}")
    best = None
    for tp in TP_GRID:
        for sl in SL_GRID:
            tr = R.backtest(df, longs, shorts, tp_pct=tp, sl_pct=sl, timeout=TIMEOUT)
            m = R.metrics(tr, "ret_pess")
            if not m:
                continue
            w5 = np.round(m["worst5_bps"], 0)
            p(f"{tp*100:5.2f}{sl*100:6.2f}{m['n']:6d}{m['wr']*100:6.1f}%{m['exp_bps']:9.1f}"
              f"{m['pf']:6.2f}{m['total_pct']:8.1f}{str(w5):>34}")
            if best is None or m["exp_bps"] > best[2]["exp_bps"]:
                best = (tp, sl, m, tr)
    p("```")
    return best


def no_stop(df, longs, shorts):
    p("\n### 3b. SIN STOP (como el stream): TP fijo 0.20%, sin SL, timeout 4h")
    tr = R.backtest(df, longs, shorts, tp_pct=0.0020, sl_pct=None, timeout=TIMEOUT)
    m = R.metrics(tr, "ret_pess")
    p("```")
    p("  " + R.fmt(m))
    if m:
        bad = tr.nsmallest(5, "ret_pess")[["t_in", "side", "ret_pess", "mae", "bars"]]
        p("  5 peores (ret_pess %, mae %, velas):")
        for _, r in bad.iterrows():
            p(f"    {str(r.t_in)[:16]}  side={int(r.side):+d}  ret={r.ret_pess*100:+6.2f}%  "
              f"mae={r.mae*100:5.2f}%  bars={int(r.bars)}")
    p("```")
    p("_Sin stop, los perdedores no se cuentan en el stream pero AQUÍ sí: mira si los 'peor5' "
      "se comen muchos ganadores (= aplanadora)._")


def report_coin(coin):
    p(f"\n{'='*78}\n## {coin}  ·  entrada {ENTRY}\n{'='*78}")
    df = R.load(coin)
    longs, shorts, tr_state = R.entries(df, **ENTRY)
    hi, lo = R.zones(df)
    n = int(longs.sum() + shorts.sum())
    span = f"{df.index[0].date()} → {df.index[-1].date()}"
    p(f"Velas: {len(df):,}  ({span}) · señales crudas: {n}  "
      f"(L {int(longs.sum())} / S {int(shorts.sum())})")

    mae_analysis(df, longs, shorts)
    best = sweep(df, longs, shorts, hi, lo)
    if best:
        tp, sl, m, trbest = best
        is_tr, oos_tr = split(trbest)
        p(f"\n**Mejor por expectancy (pess): TP={tp*100:.2f}% SL={sl*100:.2f}%**")
        p("```")
        p(f"  GLOBAL : {R.fmt(m)}")
        p(f"  IS<2026: {R.fmt(R.metrics(is_tr, 'ret_pess'))}")
        p(f"  OOS2026: {R.fmt(R.metrics(oos_tr, 'ret_pess'))}")
        mo = R.metrics(trbest, "ret_opt")
        p(f"  (banda optimista TP-first: exp={mo['exp_bps']:+.1f}bps WR={mo['wr']*100:.1f}%)")
        p("```")
    no_stop(df, longs, shorts)


if __name__ == "__main__":
    p(f"# Backtest honesto — réplica S/D 1m\n")
    p(f"Datos: Binance perps 1m · costos taker {R.__dict__.get('FEE', 0.00045)*100 if False else 0.045}%/lado "
      f"+ slip 0.02% · IS<2026-01 / OOS 2026 · banda intrabar pess/opt\n")
    for c in COINS:
        report_coin(c)
    with open("backtest_sd_matrix.md", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    p(f"\n→ guardado en backtest_sd_matrix.md")
