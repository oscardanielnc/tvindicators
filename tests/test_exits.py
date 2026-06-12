# Test sintetico del motor de salidas: verifica que SL/flip/timeout se detectan
# en velas INTERMEDIAS (el bug corregido), no solo en la ultima.
# Uso: python -m tests.test_exits
import os
import tempfile
from datetime import datetime, timedelta

os.environ["TVBOT_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

import numpy as np
import pandas as pd

import config
from tvbot import data, db, engine
from tvbot.engine import PaperEngine

data.funding_since = lambda *a, **k: 0.0      # sin red en tests

LIMA = config.LIMA_TZ


def mk_df(n_bars, tf_s, prices):
    """DataFrame de velas cerradas terminando 'ahora' (alineado al tf)."""
    now = datetime.now(LIMA)
    cur_start = int(now.timestamp() // tf_s) * tf_s
    starts = [cur_start - tf_s * (n_bars - i) for i in range(n_bars)]
    rows = []
    for i, st in enumerate(starts):
        o = h = l = c = prices.get(i, 100.0)
        if isinstance(prices.get(i), tuple):
            o, h, l, c = prices[i]
        rows.append({"ts": st * 1000, "open": o, "high": h, "low": l, "close": c,
                     "volume": 1.0})
    df = pd.DataFrame(rows)
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("dt"), starts


def open_trade(sid, side, entry_px, stop_px, bars_ago, tf_s, timeout_h=48):
    t_entry = datetime.now(LIMA) - timedelta(seconds=tf_s * bars_ago)
    return db.insert_trade(
        strategy_id=sid, strategy_name="test", symbol="TRX/USDT:USDT",
        tf="15m" if tf_s == 900 else "1h", side=side, status="open",
        t_signal=t_entry.isoformat(timespec="seconds"),
        t_entry=t_entry.isoformat(timespec="seconds"),
        entry_px=entry_px, base_amount=100.0, leverage=5.0, notional=500.0,
        qty=500.0 / entry_px, stop_px=stop_px,
        timeout_at=(t_entry + timedelta(hours=timeout_h)).isoformat(timespec="seconds"),
        atr_entry=1.0, signal_meta="{}")


def closed(tid):
    with db.conn() as c:
        return dict(c.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone())


db.init()
eng = PaperEngine()
TF = 3600

# --- TEST 1 (el bug): SL tocado hace 5 velas, NO en la ultima -> debe detectarse
df, _ = mk_df(20, TF, {i: (100, 101, 99, 100) for i in range(20)} |
              {15: (100, 101, 89.0, 100)})           # low=89 toca stop=90 en vela -5
tid = open_trade("S1", "long", 100.0, 90.0, bars_ago=10, tf_s=TF)
eng._manage_exits({("TRX/USDT:USDT", "1h"): (df, 100.0)}, ["1h"])
t = closed(tid)
assert t["status"] == "closed" and t["exit_reason"] == "SL" and t["exit_px"] == 90.0, t
print("TEST 1 OK  - SL en vela intermedia detectado (bug corregido)")

# --- TEST 2: sin toque de stop -> sigue abierto
tid = open_trade("S1", "long", 100.0, 90.0, bars_ago=10, tf_s=TF)
df2, _ = mk_df(20, TF, {i: (100, 101, 99, 100) for i in range(20)})
eng._manage_exits({("TRX/USDT:USDT", "1h"): (df2, 100.0)}, ["1h"])
assert closed(tid)["status"] == "open"
print("TEST 2 OK  - sin stop tocado, posicion sigue abierta")

# --- TEST 3: timeout por conteo de velas (49 velas 1h > 48)
tid2 = open_trade("S1", "long", 100.0, 90.0, bars_ago=50, tf_s=TF)
df3, _ = mk_df(60, TF, {i: (100, 101, 99, 100) for i in range(60)})
eng._manage_exits({("TRX/USDT:USDT", "1h"): (df3, 100.0)}, ["1h"])
t = closed(tid2)
assert t["status"] == "closed" and t["exit_reason"] == "timeout", t
print("TEST 3 OK  - timeout por conteo de velas")

# --- TEST 4: short con SL arriba en vela intermedia
tid3 = open_trade("S4", "short", 100.0, 110.0, bars_ago=10, tf_s=TF)
df4, _ = mk_df(20, TF, {i: (100, 101, 99, 100) for i in range(20)} |
               {14: (100, 112.0, 99, 100)})
eng._manage_exits({("TRX/USDT:USDT", "1h"): (df4, 100.0)}, ["1h"])
t = closed(tid3)
assert t["status"] == "closed" and t["exit_reason"] == "SL" and t["exit_px"] == 110.0, t
print("TEST 4 OK  - SL de short en vela intermedia")

print("\nTODOS LOS TESTS PASARON")
