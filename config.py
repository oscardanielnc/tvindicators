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
MARGIN_PCT = float(os.getenv("TVBOT_MARGIN_PCT", "0.10"))      # margen fijo por trade ($100 de $1000)
LEVERAGE = float(os.getenv("TVBOT_LEVERAGE", "5"))             # leverage de FALLBACK (si no hay stop)
MARGIN_MODE = os.getenv("TVBOT_MARGIN_MODE", "fixed")          # fixed = 10% del capital inicial

# --- Sizing por RIESGO (leverage dinámico por volatilidad) ---
# Cada trade arriesga RISK_PER_TRADE del capital si toca el stop. El leverage se deriva de la
# distancia al stop (ATR de cada moneda): leverage = R*capital / (dist_stop * margen). Margen fijo.
# Ver METODOLOGIA_PRODUCCION.md §5/§5.1. R calibrado a maxDD anual <=25% al p95 (calibra_R.py).
RISK_PER_TRADE = float(os.getenv("TVBOT_RISK_PER_TRADE", "0.005"))  # 0.5% del capital por trade
MAX_LEVERAGE = float(os.getenv("TVBOT_MAX_LEVERAGE", "10"))         # tope de seguridad (liquidación)

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

# --- Gates de producción (graduación de paper -> capital real) ---
# Por estrategia: pasa a producción si cumple TODO esto en vivo.
GATE_MIN_TRADES = int(os.getenv("TVBOT_GATE_TRADES", "20"))     # nº trades cerrados vivos
GATE_MIN_RATIO = float(os.getenv("TVBOT_GATE_RATIO", "0.30"))   # exp_live / exp_backtest (conserva >=30% del edge)
GATE_MIN_PF = float(os.getenv("TVBOT_GATE_PF", "1.2"))          # profit factor vivo
# Por cartera: lote 1 a producción si el track AGREGADO confirma el backtest.
GATE_PORT_MIN_TRADES = int(os.getenv("TVBOT_GATE_PORT_TRADES", "150"))
GATE_PORT_MIN_CONFIRMED = int(os.getenv("TVBOT_GATE_PORT_CONFIRMED", "8"))  # nº estrategias confirmadas

# --- API ---
API_HOST = os.getenv("TVBOT_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("TVBOT_API_PORT", "8090"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
