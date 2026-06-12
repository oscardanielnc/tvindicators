"""CLI:
  python -m tvbot            -> bucle continuo (orquestador)
  python -m tvbot --once     -> un solo ciclo (smoke test, evalua 15m y 1h)
"""
import sys

from . import logging_setup

logging_setup.setup()

if "--once" in sys.argv:
    from .engine import PaperEngine
    PaperEngine().run_cycle(["15m", "1h"])
    print("ciclo unico OK")
else:
    from .orchestrator import main
    main()
