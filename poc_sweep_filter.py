# PoC: ¿mejora el roster si exigimos un BARRIDO DE LIQUIDEZ precedente a la entrada?
# Toma las entradas REALES del roster (vectorizadas desde tvbot.indicators, identicas al
# bot) y compara baseline vs filtrado, con el MISMO motor de salida (paridad engine.py):
#   entrada open[i+1]; atrstop = SL 2xATR(senal) + timeout 48h; flip = ST contrario / TM-rojo
#   (S2, con SL seguridad 3xATR). Una posicion por estrategia. Costos: maker entrada,
#   taker+slip en SL, maker en timeout/flip. (Funding omitido: afecta igual a ambos lados.)
import numpy as np
import pandas as pd
from tvbot import indicators as I

DATA = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/{tf}.parquet"
MAKER, TAKER, SLIP = 0.0002, 0.00045, 0.0002
WARM = 300
FILTERS = [3, 6, 12, 24]      # barrido dentro de las ultimas F velas antes de la entrada

# --- barridos de liquidez (igual que poc_liquidity) ---
W, MAXAGE = 5, 200
def detect_sweeps(df):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    ph = (df["high"] == df["high"].rolling(2*W+1, center=True).max()).values
    pl = (df["low"] == df["low"].rolling(2*W+1, center=True).min()).values
    n = len(df); sL = np.zeros(n, bool); sS = np.zeros(n, bool)
    last_sh = last_sl = np.nan; sh_age = sl_age = 10**9; sh_used = sl_used = True
    for t in range(WARM, n):
        j = t - W
        if ph[j]: last_sh, sh_age, sh_used = h[j], 0, False
        if pl[j]: last_sl, sl_age, sl_used = l[j], 0, False
        sh_age += 1; sl_age += 1
        if (not sh_used) and sh_age <= MAXAGE and not np.isnan(last_sh) and h[t] > last_sh and c[t] < last_sh:
            sS[t] = True; sh_used = True
        if (not sl_used) and sl_age <= MAXAGE and not np.isnan(last_sl) and l[t] < last_sl and c[t] > last_sl:
            sL[t] = True; sl_used = True
    return sL, sS

def recent(sig, F):
    """True en i si hubo sweep en [i-F+1, i]."""
    out = np.zeros(len(sig), bool); acc = 0
    from collections import deque
    dq = deque()
    for i in range(len(sig)):
        dq.append(sig[i])
        if len(dq) > F: dq.popleft()
        out[i] = any(dq)
    return out

# --- entradas del roster (replican strategies.py, full-array) ---
def entries(coin, df):
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    up, dn, sd = I.st_flips(df)
    e = {}
    if coin == "TRX":
        gl, _, _, _ = I.bx_parts(c); e["S1"] = ("atrstop", None, gl)
        e["S2"] = ("flip", 3.0, I.tm_align_edge(c))   # flip TM-rojo (usa safety 3ATR)
    return e

# generico por estrategia (definido afuera para todas las monedas)
def roster_entries(coin, df):
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    up, dn, sd = I.st_flips(df)
    out = {}
    if coin == "TRX":
        gl, _, _, _ = I.bx_parts(c)
        hc = I.hacolt(o, h, l, c); sl, _ = I.ribbon_strength(c, h, l)
        out["S1-TRX-L"] = (+1, "atrstop", None, gl)
        out["S2-TRX-L"] = (+1, "flip", 3.0, I.tm_align_edge(c))
        out["S3-TRX-L"] = (+1, "flip", None, up & (hc == 1) & (sl >= 8))
    if coin == "XRP":
        hc = I.hacolt(o, h, l, c)
        out["S6-XRP-L"] = (+1, "flip", None, up & (hc == 1))
    if coin == "AVAX":
        hc = I.hacolt(o, h, l, c); don = I.dch_trend(c, h, l, 20)
        out["S7-AVAX-L"] = (+1, "flip", None, up & (don == 1) & (hc == 1))
    if coin == "BTC":
        sl, _ = I.ribbon_strength(c, h, l); _, _, regup, _ = I.bx_parts(c)
        full = sl == 10; ev = full & ~np.roll(full, 1)
        out["S9-BTC-L"] = (+1, "atrstop", None, ev & regup & (sd == 1))
    if coin == "SUI":
        _, rs, _, regdn = I.bx_parts(c)
        out["S4-SUI-S"] = (-1, "atrstop", None, rs & regdn)
    if coin == "LTC":
        don = I.dch_trend(c, h, l, 20)
        out["S5-LTC-S"] = (-1, "atrstop", None, dn & (don == -1))
    if coin == "ETH":
        _, rs, _, _ = I.bx_parts(c); don = I.dch_trend(c, h, l, 20)
        out["S8-ETH-S"] = (-1, "atrstop", None, rs & (don == -1))
    return out, (up, dn)

def run(df, side, exit_mode, safety_atr, entry, flips, tf):
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    atr = I.atr14(df).values; idx = df.index; n = len(df)
    up, dn = flips
    flip_arr = (dn if side > 0 else up)            # ST gira en contra
    to_bars = int(48 * 3600 / (900 if tf == "15m" else 3600))
    amult = 2.0 if exit_mode == "atrstop" else safety_atr
    trades = []; i = WARM
    while i < n - 1:
        if not entry[i]:
            i += 1; continue
        e_i = i + 1; epx = op[e_i]
        stop = epx - side * amult * atr[i] if amult else None
        exit_px = cost_out = None
        j = e_i
        while j < n - 1:
            if stop is not None:
                hit = lo[j] <= stop if side > 0 else hi[j] >= stop
                if hit:
                    exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                    cost_out = TAKER + SLIP; break
            if exit_mode == "atrstop":
                if j - e_i + 1 >= to_bars:
                    exit_px, cost_out = op[j + 1], MAKER; break
            elif flip_arr[j]:
                exit_px, cost_out = op[j + 1], MAKER; break
            j += 1
        if exit_px is None:
            break
        gross = side * (exit_px / epx - 1)
        trades.append((idx[e_i], gross - MAKER - cost_out))
        i = j + 1                                   # una posicion a la vez
    if not trades:
        return None
    return pd.DataFrame(trades, columns=["t_in", "ret"])

def metrics(tr, label):
    if tr is None or len(tr) == 0:
        return dict(var=label, trades=0)
    r = tr["ret"]; eq = (1 + r).cumprod()
    w, ls = r[r > 0], r[r <= 0]
    pf = w.sum() / abs(ls.sum()) if ls.sum() != 0 else np.inf
    by = tr.assign(y=tr["t_in"].dt.year).groupby("y")["ret"].mean() * 1e4
    yrs = " ".join(f"{y}:{v:+.0f}" for y, v in by.items())
    pos_yrs = (by > 0).sum()
    return dict(var=label, trades=len(tr), wr=f"{(r>0).mean():.0%}", PF=round(pf, 2),
                exp_bps=round(r.mean()*1e4, 1), tot=f"{(eq.iloc[-1]-1)*100:+.0f}%",
                yr_ok=f"{pos_yrs}/{by.size}", bps_x_anio=yrs)

TFMAP = {"S3-TRX-L": "15m", "S7-AVAX-L": "15m"}
COINS = ["TRX", "XRP", "AVAX", "BTC", "SUI", "LTC", "ETH"]
for coin in COINS:
    for tf in ["1h", "15m"]:
        df = pd.read_parquet(DATA.format(c=coin, tf=tf))
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        ents, flips = roster_entries(coin, df)
        sL, sS = detect_sweeps(df)
        for sid, (side, em, sa, entry) in ents.items():
            if TFMAP.get(sid, "1h") != tf:
                continue
            sweep = sL if side > 0 else sS
            base = run(df, side, em, sa, entry, flips, tf)
            print(f"\n{'='*100}\n{sid}  ({tf})")
            rows = [metrics(base, "BASELINE (sin filtro)")]
            for F in FILTERS:
                rec = recent(sweep, F)
                filt = entry & rec
                rows.append(metrics(run(df, side, em, sa, filt, flips, tf), f"+sweep<= {F} velas"))
            print(pd.DataFrame(rows).to_string(index=False))
