"""Batch 7b: ICT Turtle Soup (Flux Charts). Estrategia completa con motor propio.
Lógica: barrido de liquidez del rango HTF previo -> confirmación MSS (swing) -> entrada
fade -> TP/SL dinámico (SL = swing ∓ atr*mult, TP = entry ± |entry-SL|*RR, RR=0.9).
Adaptado a 1h con HTF=4h (barLength=4). Costos + funding reales. IS/OOS. Evaluación honesta.
Uso: python poc_turtlesoup.py
"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_indicadores_nuevos.py", encoding="utf-8").read()
exec(src.split("def main(")[0])  # I, DATA, MAKER, TAKER, SLIP, WARM, load_fund, all_coins

BARLEN = 4        # HTF 4h / TF 1h
MSS = 10          # swing length
RR = 0.9
RISK = {"Highest": 10, "High": 6.5, "Normal": 5.5, "Low": 3.5, "Lowest": 1.15}


def backtest_ts(df, ft, fr, sl_mult=3.5):
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    atr = I.pine_rma(pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
                                (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1), 5).values
    hh4 = pd.Series(h).rolling(BARLEN).max().shift(1).values    # rango HTF previo
    ll4 = pd.Series(l).rolling(BARLEN).min().shift(1).values
    hhMSS = pd.Series(h).rolling(MSS).max().values
    llMSS = pd.Series(l).rolling(MSS).min().values
    idx = df.index; ivms = idx.view("int64") / 1e6; n = len(df)
    trades = []; i = WARM
    state = "wait"; etype = None
    while i < n - 1:
        if state == "wait":
            if not np.isnan(ll4[i]) and l[i] < ll4[i]:      # barrido sellside -> Long (classic)
                etype, state = "Long", "exec"
            elif not np.isnan(hh4[i]) and h[i] > hh4[i]:    # barrido buyside -> Short
                etype, state = "Short", "exec"
            i += 1; continue
        if state == "exec":
            entered = False
            if etype == "Long" and h[i] > hhMSS[i - 1]:
                e_i = i + 1
                if e_i >= n:
                    break
                epx = o[e_i]; sl = llMSS[i] - atr[i] * sl_mult; tp = epx + abs(epx - sl) * RR
                entered = True; side = 1
            elif etype == "Short" and l[i] < llMSS[i - 1]:
                e_i = i + 1
                if e_i >= n:
                    break
                epx = o[e_i]; sl = hhMSS[i] + atr[i] * sl_mult; tp = epx - abs(epx - sl) * RR
                entered = True; side = -1
            if not entered:
                i += 1; continue
            # gestionar salida TP/SL
            exit_px = cost_out = t_out = None; j = e_i
            while j < n - 1:
                if side > 0:
                    if l[j] <= sl:
                        exit_px, cost_out, t_out = min(o[j], sl), TAKER + SLIP, j; break
                    if h[j] >= tp:
                        exit_px, cost_out, t_out = max(o[j], tp), MAKER, j; break
                else:
                    if h[j] >= sl:
                        exit_px, cost_out, t_out = max(o[j], sl), TAKER + SLIP, j; break
                    if l[j] <= tp:
                        exit_px, cost_out, t_out = min(o[j], tp), MAKER, j; break
                j += 1
            if exit_px is None:
                break
            a, b = np.searchsorted(ft, ivms[e_i]), np.searchsorted(ft, ivms[t_out])
            net = side * (exit_px / epx - 1) - MAKER - cost_out - side * fr[a:b].sum()
            trades.append((idx[e_i], net)); i = t_out + 1; state = "wait"
            continue
        i += 1
    return pd.DataFrame(trades, columns=["t_in", "ret"]) if trades else None


def met(tr):
    if tr is None or len(tr) == 0:
        return None
    r = tr["ret"]; by = tr.assign(y=tr["t_in"].dt.year).groupby("y")["ret"].mean()
    return dict(n=len(tr), wr=(r > 0).mean()*100, exp=r.mean()*1e4,
                pf=r[r > 0].sum()/max(abs(r[r <= 0].sum()), 1e-9), ypos=int((by > 0).sum()), ytot=int(len(by)))


def split(tr, cut="2025-01-01"):
    if tr is None:
        return None, None
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


def main():
    coins = all_coins()
    print(f"ICT Turtle Soup · 1h (HTF 4h) · RR {RR} · SL {RISK['Low']}×ATR · costos+funding reales", flush=True)
    agg = []   # PnL agregado de todas las monedas (la estrategia es 1 setup, multi-moneda)
    rows = []
    for coin in coins:
        try:
            df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
        except Exception:
            continue
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        try:
            ft, fr = load_fund(coin)
        except Exception:
            continue
        tr = backtest_ts(df, ft, fr)
        m = met(tr)
        if m:
            mi, mo = split(tr)
            rows.append((coin, m, mi, mo))
            agg.append(tr.assign(coin=coin))
    A = pd.concat(agg)
    am = met(A); ai, ao = split(A)
    print(f"\n{'='*78}\nAGREGADO (todas las monedas, costos reales)")
    print(f"  n={am['n']}  WR={am['wr']:.0f}%  exp={am['exp']:.1f} bps  PF={am['pf']:.2f}  años+={am['ypos']}/{am['ytot']}")
    print(f"  IS<2025: n={ai['n']} exp={ai['exp']:.1f}  ·  OOS>=2025: n={ao['n']} exp={ao['exp']:.1f}")
    print(f"  edge BRUTO (exp + ~13bps costo): {am['exp']+13:.1f} bps")
    # por moneda: cuántas tienen exp>0 robusto
    good = [(c, m, mi, mo) for c, m, mi, mo in rows if m["n"] >= 40 and m["exp"] > 0 and m["pf"] >= 1.4
            and mi and mo and mi["exp"] > 0 and mo["exp"] > 0]
    print(f"\nMonedas con setup robusto (n>=40, exp>0, PF>=1.4, IS>0 y OOS>0): {len(good)}/{len(rows)}")
    for c, m, mi, mo in sorted(good, key=lambda x: x[3]["exp"], reverse=True)[:15]:
        print(f"  {c:6} n={m['n']:4} WR={m['wr']:3.0f}% exp={m['exp']:5.0f} PF={m['pf']:.2f} IS={mi['exp']:5.0f} OOS={mo['exp']:5.0f}")


if __name__ == "__main__":
    main()
