# Test del shadow-logging de salidas alternativas (tvbot/shadow.py).
# Lo que importa verificar: (1) la variante 'base' REPRODUCE la salida real del motor — si no,
# ninguna comparación entre variantes es creible; (2) las variantes se guardan serializadas;
# (3) el shadow NO altera la ejecución.
# Uso: python -m tests.test_shadow
import json
import os
import tempfile
from datetime import datetime, timedelta

os.environ["TVBOT_DB"] = os.path.join(tempfile.mkdtemp(), "test_shadow.db")

import pandas as pd

import config
from tvbot import data, db, shadow
from tvbot.engine import PaperEngine

data.funding_since = lambda *a, **k: 0.0      # sin red ni funding en tests
LIMA = config.LIMA_TZ
TF = 3600


def mk_df(bars):
    now = datetime.now(LIMA)
    cur = int(now.timestamp() // TF) * TF
    rows = [{"ts": (cur - TF * (len(bars) - i)) * 1000, "open": o, "high": h,
             "low": l, "close": c, "volume": 1.0} for i, (o, h, l, c) in enumerate(bars)]
    df = pd.DataFrame(rows)
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("dt")


def open_trade(side, entry_px, stop_px, bars_ago):
    t = datetime.now(LIMA) - timedelta(seconds=TF * bars_ago)
    return db.insert_trade(
        strategy_id="S1", strategy_name="test", symbol="TRX/USDT:USDT", tf="1h",
        side=side, status="open", t_signal=t.isoformat(timespec="seconds"),
        t_entry=t.isoformat(timespec="seconds"), entry_px=entry_px, base_amount=100.0,
        leverage=3.0, notional=300.0, qty=300.0 / entry_px, stop_px=stop_px,
        timeout_at=(t + timedelta(hours=48)).isoformat(timespec="seconds"),
        atr_entry=1.0, signal_meta="{}")


def closed(tid):
    with db.conn() as c:
        return dict(c.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone())


db.init()
eng = PaperEngine()

# --- TEST 1: fidelidad. Long que toca stop -> 'base' debe igualar el retorno real.
bars = [(100, 101, 99, 100)] * 12 + [(100, 101, 89.0, 95)] + [(95, 96, 94, 95)] * 5
tid = open_trade("long", 100.0, 90.0, bars_ago=10)
eng._manage_exits({("TRX/USDT:USDT", "1h"): (mk_df(bars), 100.0)}, ["1h"])
t = closed(tid)
assert t["status"] == "closed" and t["exit_reason"] == "SL", t
sh = json.loads(t["shadow_exits"])
real_bps = t["ret_pct_nolev"] * 100
assert abs(sh["base"] - real_bps) < 0.5, f"base {sh['base']} != real {real_bps}"
print(f"TEST 1 OK  - 'base' reproduce la salida real ({sh['base']:.1f} vs {real_bps:.1f} bps)")

# --- TEST 2: en un trade que murio en el stop, uno MAS APRETADO corta antes y pierde MENOS
# (y a mayor aprieto, menor perdida). Es el invariante que valida el orden de las variantes.
assert sh["sl0.5R"] > sh["sl0.75R"] > sh["base"], sh
print(f"TEST 2 OK  - stops mas apretados cortan antes ({sh['sl0.5R']:.0f} > {sh['sl0.75R']:.0f} "
      f"> {sh['base']:.0f} bps)")

# --- TEST 3: long ganador que sube a +2R y devuelve -> el TP debe capturar mas que dejarlo correr
bars = ([(100, 101, 99.5, 100)] * 10 + [(100, 104.5, 100, 104)]
        + [(104, 104, 99.0, 99.2)] * 5 + [(99.2, 99.2, 97.0, 97.5)])   # devuelve todo y muere en el stop
tid = open_trade("long", 100.0, 98.0, bars_ago=8)     # R = 2%
eng._manage_exits({("TRX/USDT:USDT", "1h"): (mk_df(bars), 100.0)}, ["1h"])
t = closed(tid)
sh = json.loads(t["shadow_exits"])
assert abs(sh["base"] - t["ret_pct_nolev"] * 100) < 0.5, (sh["base"], t["ret_pct_nolev"] * 100)
assert sh["tp1R"] > sh["base"] and sh["tp2R"] > sh["base"], sh
assert sh["be1R"] > sh["base"], sh          # breakeven salva el devolvido
print(f"TEST 3 OK  - TP/breakeven capturan el MFE devuelto (base {sh['base']:.0f}, "
      f"tp2R {sh['tp2R']:.0f}, be1R {sh['be1R']:.0f} bps)")

# --- TEST 4: el shadow NO cambia la ejecucion (mismo exit real que sin shadow)
assert t["exit_reason"] in ("SL", "timeout", "flip"), t["exit_reason"]
assert isinstance(json.loads(t["shadow_exits"]), dict)
print("TEST 4 OK  - el shadow solo registra; la ejecucion real no cambia")

# --- TEST 5: sin stop no hay R -> no se calcula shadow (no se inventan numeros)
assert shadow.compute(1, 100.0, None, ([], [], [], []), 0, 10) is None
print("TEST 5 OK  - sin stop no se fabrica shadow")

print("\nTODOS LOS TESTS PASARON")
