# Tabla consolidada de candidatos (sweep1 validados + sweep2 pendientes), con funding real
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/sweep2.py"), encoding="utf-8").read()
exec(src.split("SKIP_BX")[0])          # solo defs: pine_*, t3, donch, supertrend_dir, prep, run

FUND = {c: (rf"D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/{c}_USDT_USDT.parquet", "ts")
        for c in ["TRX", "ETH", "BTC", "LTC", "DOT"]}
FUND["SUI"] = (r"C:/Users/LENOVO/kepler/data/funding/SUIUSDT.parquet", "funding_time")

def load_fund(coin):
    p, tcol = FUND[coin]
    f = pd.read_parquet(p)
    return pd.to_datetime(f[tcol], unit="ms").values.astype("datetime64[ns]"), f["funding_rate"].astype(float).values

# (nombre, coin, tf, side, trigger, filtros, exit, estado)
CONFIGS = [
    ("TRX L | B-Xtrender",        "TRX", "1h",  1, "BX",   [],             "atrstop", "VALIDADO"),
    ("SUI S | B-Xtrender+reg",    "SUI", "1h", -1, "BX",   ["BXreg"],      "atrstop", "VALIDADO"),
    ("ETH S | B-Xtrender+Donch",  "ETH", "1h", -1, "BX",   ["Don"],        "atrstop", "VALIDADO"),
    ("TRX L | TrendMeter",        "TRX", "1h",  1, "TM",   [],             "atrstop", "pendiente"),
    ("TRX L | Supertrend",        "TRX", "15m", 1, "ST",   [],             "flip",    "pendiente"),
    ("BTC L | TM+WaveTrend+ST",   "BTC", "1h",  1, "TMWT", ["ST"],         "atrstop", "pendiente"),
    ("LTC S | Supertrend+Donch",  "LTC", "1h", -1, "ST",   ["Don"],        "atrstop", "pendiente"),
    ("DOT S | Supertrend+BXreg",  "DOT", "1h", -1, "ST",   ["BXreg"],      "atrstop", "pendiente"),
]

# nota: sweep1 usaba BX con filtro implicito T3<0 — prep() de sweep2 ya lo incluye en el trigger BX
rows = []
for name, coin, tf, side, trig, fils, exname, estado in CONFIGS:
    df, atrv, triggers, regimes, st_exits = prep(coin, tf)
    ent = (triggers[trig][0 if side > 0 else 1]).copy()
    for f in fils:
        ent &= regimes[f][0 if side > 0 else 1]
    exm = None if exname == "atrstop" else (st_exits[0] if side > 0 else st_exits[1])
    # motor con registro de barras por trade
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    idx = df.index; n = len(df)
    bpd = 96 if tf == "15m" else 24
    to_bars = TIMEOUT_H * bpd // 24
    ft, fr = load_fund(coin)
    trades, j_free = [], 0
    for i_sig in np.flatnonzero(ent[WARMUP:n-2]) + WARMUP:
        if i_sig < j_free: continue
        e_i = i_sig + 1; epx = op[e_i]
        stop = epx - side * ATR_MULT * atrv[i_sig]
        j, exit_px, cost_out, t_out = e_i, None, MAKER, None
        while j < n - 1:
            if exname == "atrstop":
                hit = lo[j] <= stop if side > 0 else hi[j] >= stop
                if hit:
                    exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                    cost_out, t_out = TAKER + SLIP, j; break
                if j - e_i + 1 >= to_bars:
                    exit_px, t_out = op[j + 1], j + 1; break
            elif exm[j]:
                exit_px, t_out = op[j + 1], j + 1; break
            j += 1
        if exit_px is None: break
        a, b = np.searchsorted(ft, idx.values[e_i]), np.searchsorted(ft, idx.values[t_out])
        net = side * (exit_px / epx - 1) - MAKER - cost_out - side * fr[a:b].sum() * -1 * -1
        net = side * (exit_px / epx - 1) - MAKER - cost_out + (-side * fr[a:b].sum())
        trades.append((idx[e_i], net, t_out - e_i))
        j_free = t_out + 1
    tr = pd.DataFrame(trades, columns=["t_in", "net", "bars"])
    r = tr["net"]
    months = (idx[-1] - idx[WARMUP]).days / 30.44
    eq = (1 + r).cumprod()
    mdd = ((eq / eq.cummax()) - 1).min()
    days = (idx[-1] - idx[WARMUP]).days
    cagr = ((eq.iloc[-1]) ** (365 / days) - 1) * 100
    pf = r[r > 0].sum() / abs(r[r <= 0].sum())
    win_h = tr.loc[r > 0, "bars"].mean() * 24 / bpd
    loss_h = tr.loc[r <= 0, "bars"].mean() * 24 / bpd
    daily = pd.Series(r.values, index=tr["t_in"].values).resample("1D").sum()
    sharpe = daily.mean() / daily.std() * np.sqrt(365)
    y = tr.groupby(tr["t_in"].dt.year)["net"].apply(lambda g: np.prod(1 + g) - 1)
    rows.append({
        "Candidato": name, "TF": tf, "Estado": estado,
        "Trades/mes": round(len(r) / months, 1),
        "WinRate": f"{(r>0).mean():.0%}",
        "H_ganador(h)": round(win_h, 1), "H_perdedor(h)": round(loss_h, 1),
        "Expect/trade": f"{r.mean()*100:+.2f}%",
        "CAGR": f"{cagr:+.0f}%", "MaxDD": f"{mdd*100:.0f}%",
        "PF": round(pf, 2), "Sharpe": round(sharpe, 2),
        "Anos+": f"{(y>0).sum()}/{len(y)}", "2026": f"{y.get(2026, np.nan)*100:+.0f}%",
    })

out = pd.DataFrame(rows)
print(out.to_string(index=False))
