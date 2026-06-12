"""Configuracion central del bot tvindicators (paper trading)."""
import os
from datetime import timedelta, timezone
from pathlib import Path

# Todo el sistema (DB, logs, API) trabaja en hora de Lima, Peru (UTC-5, sin DST)
LIMA_TZ = timezone(timedelta(hours=-5), name="America/Lima")

ROOT = Path(__file__).parent
DATA_DIR = Path(os.getenv("TVBOT_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.getenv("TVBOT_DB", DATA_DIR / "tvbot.db"))
LOG_DIR = Path(os.getenv("TVBOT_LOG_DIR", DATA_DIR / "logs"))

# --- Capital simulado ---
CAPITAL_INICIAL = float(os.getenv("TVBOT_CAPITAL", "1000"))
MARGIN_PCT = float(os.getenv("TVBOT_MARGIN_PCT", "0.10"))      # 10% fijo por trade
LEVERAGE = float(os.getenv("TVBOT_LEVERAGE", "5"))             # 5x fijo
MARGIN_MODE = os.getenv("TVBOT_MARGIN_MODE", "fixed")          # fixed = 10% del capital inicial

# --- Costos (identicos al backtest validado) ---
MAKER_FEE = 0.0002
TAKER_FEE = 0.00045
SLIPPAGE = 0.0002          # se aplica en salidas por stop (market)

# --- Ejecucion ---
EXCHANGE = os.getenv("TVBOT_EXCHANGE", "binanceusdm")
WARMUP_BARS = 1000          # HACOLT/TEMA55 necesitan cola larga
CYCLE_OFFSET_S = 20         # corre 20s despues del cierre de vela
TIMEOUT_HOURS = 48
ATR_MULT = 2.0
CIRCUIT_BREAKER_ERRORS = 5  # errores consecutivos -> pausa
CIRCUIT_BREAKER_PAUSE_S = 900

# --- API ---
API_HOST = os.getenv("TVBOT_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("TVBOT_API_PORT", "8090"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
