"""UTD19 Traffic Data Warehouse and Decision Support System Engine."""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

__version__ = "0.1.0"
