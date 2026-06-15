"""Batch 2: REVERSION A LA MEDIA (clase nueva, motor de salida distinto).

El roster (29) es todo continuacion/ruptura: entra y deja correr (ATR-stop/flip/timeout).
La reversion es lo opuesto: entra en un EXTREMO (sobreventa/sobrecompra dentro de tendencia)
y sale al VOLVER A LA MEDIA. Necesita su propio motor (run_mr): exit cuando el precio
recupera la media corta, SL por ATR, timeout corto.

Senales probadas:
  1) CRSI2 (Connors): long = close>SMA(trend) & RSI(2)<thr  (comprar el dip en tendencia alcista)
                      short = close<SMA(trend) & RSI(2)>100-thr
  2) BB%b: long = close<banda inferior & tendencia alcista ; short simetrico

Exit: close cruza de vuelta su SMA(exit_len)  ->  open siguiente (maker)
      SL = entrada ∓ stop_atr×ATR (taker+slip) · timeout to_h horas.
Costos + funding reales. Gate = exp>0, PF>=1.4, n>=40, años+ (tol1) Y OOS(>=2025) exp>0, n>=12.

Uso: python poc_meanrev.py
"""
import os
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_indicadores_nuevos.py", encoding="utf-8").read()
exec(src.split("def main(")[0])   # I, DATA, MAKER, TAKER, SLIP, WARM, load_fund, met, all_coins, roster_pnl_daily...


def run_mr(df, side, entry, target_ma, stop_atr, to_bars, ft, fr):
    """Motor de reversion: sale cuando close recupera target_ma (la media), o SL, o timeout."""
    op, hi, lo, cl = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    atr = I.atr14(df).values; idx = df.index; n = len(df)
    tgt = np.asarray(target_ma)
    ivms = idx.view("int64") / 1e6
    trades = []; i = WARM
    while i < n - 1:
        if not entry[i]:
            i += 1; continue
        e_i = i + 1; epx = op[e_i]
        stop = epx - side * stop_atr * atr[i]
        exit_px = cost_out = t_out = None; j = e_i
        while j < n - 1:
            hit = lo[j] <= stop if side > 0 else hi[j] >= stop
            if hit:
                exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                cost_out, t_out = TAKER + SLIP, j; break
            reverted = cl[j] >= tgt[j] if side > 0 else cl[j] <= tgt[j]
            if reverted:
                exit_px, cost_out, t_out = op[j + 1], MAKER, j + 1; break
            if j - e_i + 1 >= to_bars:
                exit_px, cost_out, t_out = op[j + 1], MAKER, j + 1; break
            j += 1
        if exit_px is None:
            break
        a, b = np.searchsorted(ft, ivms[e_i]), np.searchsorted(ft, ivms[t_out])
        net = side * (exit_px / epx - 1) - MAKER - cost_out - side * fr[a:b].sum()
        trades.append((idx[e_i], net)); i = j + 1
    return pd.DataFrame(trades, columns=["t_in", "ret"]) if trades else None


def split_met(tr, cut="2025-01-01"):
    if tr is None:
        return None, None
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


def signals(df, sig, side, thr, trend_len):
    """Devuelve el array de entrada (evento booleano) para el tipo de senal."""
    c = df["close"]
    sma_t = c.rolling(trend_len).mean().values
    up_trend = c.values > sma_t; dn_trend = c.values < sma_t
    if sig == "CRSI":
        rsi2 = I.pine_rsi(c, 2).values
        if side > 0:
            cond = up_trend & (rsi2 < thr)
        else:
            cond = dn_trend & (rsi2 > 100 - thr)
    else:  # BB%b
        basis = c.rolling(20).mean(); dev = 2.0 * c.rolling(20).std(ddof=0)
        lo_b, up_b = (basis - dev).values, (basis + dev).values
        if side > 0:
            cond = up_trend & (c.values < lo_b)
        else:
            cond = dn_trend & (c.values > up_b)
    # evento: primer cruce a la condicion (evita re-marcar cada vela del extremo)
    ev = cond & ~np.roll(cond, 1); ev[0] = False
    return ev


def target(df, exit_len):
    return df["close"].rolling(exit_len).mean().values


# combos (pequeño, para no sobreajustar): (sig, thr, trend_len, exit_len, stop_atr)
COMBOS = [
    ("CRSI", 5,  100, 5,  3.0), ("CRSI", 10, 100, 5,  3.0),
    ("CRSI", 5,  200, 10, 3.0), ("CRSI", 10, 200, 20, 3.0),
    ("BB%b", 0,  100, 20, 3.0), ("BB%b", 0,  200, 20, 3.0),
]
TO_H = 24  # timeout corto: la reversion debe ser rapida


def main():
    coins = all_coins()
    print(f"Universo: {len(coins)} monedas · TF 1h · REVERSION (CRSI2 + BB%b)", flush=True)
    survivors = []
    for ci, coin in enumerate(coins, 1):
        try:
            df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
        except Exception:
            continue
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        try:
            ft, fr = load_fund(coin)
        except Exception:
            continue
        for side, tag in ((+1, "L"), (-1, "S")):
            for sig, thr, tl, el, sa in COMBOS:
                ev = signals(df, sig, side, thr, tl)
                tgt = target(df, el)
                tr = run_mr(df, side, ev, tgt, sa, TO_H, ft, fr)
                m = met(tr)
                if not m or m["n"] < 40 or m["exp"] <= 0 or m["pf"] < 1.4 or m["ypos"] < m["ytot"] - 1:
                    continue
                mi, mo = split_met(tr)
                if not mo or mo["exp"] <= 0 or mo["n"] < 12:
                    continue
                survivors.append((coin, f"{sig}-{tag}", f"thr{thr}/t{tl}/x{el}", m, mi, mo))
        print(f"  [{ci}/{len(coins)}] {coin}", end="\r", flush=True)

    print(" " * 50)
    print(f"{'='*104}")
    print(f"SUPERVIVIENTES REVERSION (full: exp>0/PF>=1.4/n>=40/años+  Y  OOS>=2025: exp>0/n>=12)")
    print(f"{'coin':6}{'señal':9}{'params':16}{'n':>5}{'WR%':>5}{'exp':>6}{'PF':>6}{'años+':>7}"
          f"{'IS_exp':>8}{'OOS_exp':>9}{'OOS_PF':>8}")
    print(f"{'-'*104}")
    for coin, sg, pr, m, mi, mo in sorted(survivors, key=lambda x: x[5]["exp"], reverse=True):
        print(f"{coin:6}{sg:9}{pr:16}{m['n']:5}{m['wr']:5.0f}{m['exp']:6.0f}{m['pf']:6.2f}"
              f"{m['ypos']:4}/{m['ytot']:<2}{mi['exp']:8.0f}{mo['exp']:9.0f}{mo['pf']:8.2f}")
    print(f"\n{len(survivors)} setups de reversion pasan full+OOS.")


if __name__ == "__main__":
    main()
