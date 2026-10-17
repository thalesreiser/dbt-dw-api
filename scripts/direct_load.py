"""RF-01 / R-P3-01: load CVM fund data into the DuckDB raw schema.

Direct download of the CVM open data (fallback while P1 is not ready) or the P1 Parquet.

Usage:
    python scripts/direct_load.py --competencia 2026-09 [--competencias 3]
    python scripts/direct_load.py --source p1-parquet --path /path/to/p1/gold
"""

from fundos_api.ingestion import main

if __name__ == "__main__":
    raise SystemExit(main())
