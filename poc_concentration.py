"""
Cuantifica la concentracion TRX-L: el roster tiene 3 estrategias LONG TRX (S1/S2/S3)
que pueden estar abiertas a la vez. Mide solapamiento, exposicion y el impacto en maxDD,
y evalua un cap de "max 1 posicion TRX-L concurrente" como posible mitigacion.

Reusa el motor de portafolio.py. S2 se reconstruye con su salida de PRODUCCION
(flip Trend Meter rojo + stop de seguridad 3xATR, sin timeout), no el atrstop viejo.
Sizing fiel al bot: cada trade = $100 margen x5 = $500 nominal sobre $1000.
"""
import numpy as np
import pandas as pd

# --- traer el motor y helpers de portafolio.py (sin correr su analisis) ---
src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\portafolio.py", encoding="utf-8").read()
exec(src.split("daily, stats =")[0])   # load_df, load_fund, atr14, engine, tm_trig, st_flips, rib_str, build, hacolt...

NOTIONAL = 500.0        # $100 margen x 5
CAPITAL  = 1000.0
START    = "2023-09-01"


def tm_red(c):
    """Salida S2 produccion: los 3 Trend Meters se alinean ROJOS (evento)."""
    fmacd = pine_ema(c, 8) - pine_ema(c, 21)
    fhist = (fmacd - pine_ema(fmacd, 5)) > 0
    neg = ((~fhist) & (pine_rsi(c, 13) < 50) & (pine_rsi(c, 5) < 50)).values
    return neg & ~np.roll(neg, 1)


def engine_flip_safety(df, atrv, ent, exm, side, ft, fr, atr_mult):
    """flip (exm) O stop de seguridad atr_mult x ATR, lo primero; sin timeout."""
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    idx = df.index; n = len(df); iv = idx.values
    trades, j_free = [], 0
    for i_sig in np.flatnonzero(ent[WARMUP:n - 2]) + WARMUP:
        if i_sig < j_free:
            continue
        e_i = i_sig + 1; epx = op[e_i]
        stop = epx - side * atr_mult * atrv[i_sig]
        j, exit_px, cost_out, t_out = e_i, None, MAKER, None
        while j < n - 1:
            hit = lo[j] <= stop if side > 0 else hi[j] >= stop
            if hit:
                exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                cost_out, t_out = TAKER + SLIP, j; break
            if exm[j]:
                exit_px, t_out = op[j + 1], j + 1; break
            j += 1
        if exit_px is None:
            break
        a, b = np.searchsorted(ft, iv[e_i]), np.searchsorted(ft, iv[t_out])
        net = side * (exit_px / epx - 1) - MAKER - cost_out + (-side * fr[a:b].sum())
        trades.append((idx[e_i], idx[t_out], net, t_out - e_i))
        j_free = t_out + 1
    return pd.DataFrame(trades, columns=["t_in", "t_out", "net", "bars"])


# ─── construir trades de las 3 TRX-L (fiel a produccion) ───
dfT1 = load_df("TRX", "1h"); ftT, frT = load_fund("TRX")
atrT = atr14(dfT1)
trS1 = engine(dfT1, atrT, bx_trig(dfT1["close"]), 1, "atrstop", None, ftT, frT)        # S1: 2xATR+48h
trS2 = engine_flip_safety(dfT1, atrT, tm_trig(dfT1["close"]), tm_red(dfT1["close"]),
                          1, ftT, frT, 3.0)                                             # S2: flip+3xATR
trS3 = build("S3 TRX-L ST+HAC+RIB 15m")[0]                                              # S3: flip ST 15m

TRXL = {"S1": trS1, "S2": trS2, "S3": trS3}
for k, t in TRXL.items():
    t = t[t["t_in"] >= START]
    TRXL[k] = t.reset_index(drop=True)
    print(f"{k}: {len(TRXL[k])} trades  WR={ (TRXL[k]['net']>0).mean():.0%}  "
          f"hold medio={TRXL[k]['bars'].mean()* (0.25 if k=='S3' else 1):.1f}h  "
          f"exp/trade={TRXL[k]['net'].mean()*100:+.2f}%")


# ─── 1) SOLAPAMIENTO: cuantas TRX-L abiertas simultaneamente ───
tl_start = min(t["t_in"].min() for t in TRXL.values())
tl_end   = max(t["t_out"].max() for t in TRXL.values())
grid = pd.date_range(tl_start, tl_end, freq="15min")
opencnt = pd.Series(0, index=grid)
per = {}
for k, t in TRXL.items():
    s = pd.Series(0, index=grid)
    for _, r in t.iterrows():
        s.loc[(grid >= r["t_in"]) & (grid < r["t_out"])] = 1
    per[k] = s
    opencnt += s

active = opencnt[opencnt > 0]
total_steps = len(grid)
print("\n=== SOLAPAMIENTO (cuantas TRX-L abiertas a la vez) ===")
print(f"  ventana analizada: {grid[0].date()} -> {grid[-1].date()}")
print(f"  % tiempo con >=1 TRX-L abierta: {(opencnt>=1).mean()*100:.1f}%")
print(f"  % tiempo con >=2 TRX-L abiertas: {(opencnt>=2).mean()*100:.1f}%")
print(f"  % tiempo con  =3 TRX-L abiertas: {(opencnt==3).mean()*100:.1f}%")
print(f"  de las horas CON exposicion, % con >=2 a la vez: {(opencnt[opencnt>0]>=2).mean()*100:.1f}%")
print(f"  exposicion nominal TRX maxima simultanea: ${opencnt.max()*NOTIONAL:.0f} "
      f"({opencnt.max()*NOTIONAL/CAPITAL*100:.0f}% del capital, {int(opencnt.max())} posiciones)")
# pares mas solapados
for a, b in [("S1", "S2"), ("S1", "S3"), ("S2", "S3")]:
    both = ((per[a] > 0) & (per[b] > 0)).sum()
    print(f"  horas-grid {a}&{b} abiertas juntas: {both*0.25:.0f}h "
          f"({both/max((per[a]>0).sum(),1)*100:.0f}% del tiempo de {a})")


# ─── 2) CORRELACION de retornos diarios entre las 3 TRX-L ───
def daily_ret(t):
    return pd.Series(t["net"].values, index=t["t_out"].values).resample("1D").sum()

Dtrx = pd.DataFrame({k: daily_ret(t) for k, t in TRXL.items()}).fillna(0.0)
Dtrx = Dtrx[Dtrx.index >= START]
print("\n=== CORRELACION retornos diarios TRX-L ===")
print(Dtrx.corr().round(2).to_string())


# ─── 3) maxDD: cluster TRX-L sin cap vs con cap de 1 posicion concurrente ───
def usd_equity(trades_list):
    """Equity en $ sumando net x NOTIONAL por fecha de cierre."""
    pnl = pd.concat([pd.Series(t["net"].values * NOTIONAL, index=t["t_out"].values)
                     for t in trades_list]).sort_index()
    daily = pnl.resample("1D").sum()
    eq = CAPITAL + daily.cumsum()
    return eq

def maxdd_usd(eq):
    return float((eq - eq.cummax()).min())

def maxdd_pct(eq):
    return float((eq / eq.cummax() - 1).min()) * 100   # % del pico (comparable al -7.3% validado)

def cap_concurrent(trades_list, cap):
    """Devuelve los trades que sobreviven a 'max cap posiciones TRX-L concurrentes'
    (greedy por orden de entrada; se descartan las entradas que exceden el cap)."""
    allt = pd.concat(trades_list).sort_values("t_in").reset_index(drop=True)
    busy = []          # lista de t_out de posiciones activas
    keep = []
    for _, r in allt.iterrows():
        busy = [b for b in busy if b > r["t_in"]]   # liberar las ya cerradas
        if len(busy) < cap:
            keep.append(r)
            busy.append(r["t_out"])
    return pd.DataFrame(keep)

uncapped = list(TRXL.values())
eq_unc = usd_equity(uncapped)
ret_unc = eq_unc.iloc[-1] - CAPITAL
print("\n=== IMPACTO maxDD del CLUSTER TRX-L (3 estrategias, $500 nominal c/u) ===")
print(f"  SIN CAP (produccion actual): retorno ${ret_unc:+.0f}  maxDD {maxdd_pct(eq_unc):.1f}% del pico "
      f"(${maxdd_usd(eq_unc):.0f})  trades={sum(len(t) for t in uncapped)}")
for cap in (2, 1):
    capt = cap_concurrent(uncapped, cap)
    eqc = usd_equity([capt])
    retc = eqc.iloc[-1] - CAPITAL
    print(f"  CAP {cap} concurrente:          retorno ${retc:+.0f}  maxDD {maxdd_pct(eqc):.1f}% del pico "
          f"(${maxdd_usd(eqc):.0f})  trades={len(capt)} "
          f"(descarta {sum(len(t) for t in uncapped)-len(capt)})")


# ─── 4) Dias de perdida conjunta: cuando hay >=2 abiertas, ¿pierden juntas? ───
joint = Dtrx[(Dtrx != 0).sum(axis=1) >= 2]    # dias con >=2 TRX-L cerrando trades
print("\n=== DIAS CON >=2 TRX-L cerrando el mismo dia ===")
print(f"  n dias: {len(joint)}")
print(f"  dias donde TODAS las activas perdieron: "
      f"{(joint[joint!=0].le(0).all(axis=1)).mean()*100:.0f}%")
print(f"  retorno medio del cluster en esos dias: {joint.sum(axis=1).mean()*100:+.2f}%  "
      f"(peor dia conjunto: {joint.sum(axis=1).min()*100:+.2f}% = ${joint.sum(axis=1).min()*NOTIONAL:+.0f})")


# ─── 5) Impacto en el PORTAFOLIO completo (9 estrategias, $500 nominal c/u) ───
ALL = {
    "S1": trS1, "S2": trS2, "S3": trS3,
    "S4": build("S4 SUI-S BX+reg 1h")[0], "S5": build("S5 LTC-S ST+Don 1h")[0],
    "S6": build("S6 XRP-L ST+HAC 1h")[0], "S7": build("S7 AVAX-L ST+Don+HAC 15m")[0],
    "S8": build("S8 ETH-S BX+Don 1h")[0], "S9": build("S9 BTC-L RIB+BXreg+ST 1h")[0],
}
ALL = {k: v[v["t_in"] >= START].reset_index(drop=True) for k, v in ALL.items()}
others = [ALL[k] for k in ("S4", "S5", "S6", "S7", "S8", "S9")]

eq_full = usd_equity(list(ALL.values()))
eq_capped = usd_equity(others + [cap_concurrent([trS1, trS2, trS3], 1)])
print("\n=== IMPACTO EN EL PORTAFOLIO COMPLETO (9 estrategias, $500 nominal c/u) ===")
print(f"  ACTUAL (TRX-L sin cap):  retorno ${eq_full.iloc[-1]-CAPITAL:+.0f}  "
      f"maxDD {maxdd_pct(eq_full):.1f}% del pico (${maxdd_usd(eq_full):.0f})")
print(f"  CON cap TRX-L=1:         retorno ${eq_capped.iloc[-1]-CAPITAL:+.0f}  "
      f"maxDD {maxdd_pct(eq_capped):.1f}% del pico (${maxdd_usd(eq_capped):.0f})")
