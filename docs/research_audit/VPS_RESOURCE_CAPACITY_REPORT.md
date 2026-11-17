# VPS Resource Capacity Report (Stage 1)
- **CPU:** 4 cores
- **RAM:** 7.8 GiB total, 5.6 GiB available (2.0 GiB swap)
- **Disk:** 71 GB available on `/` (26% used)
- **Runtimes:** Python 3.12.3 installed; Docker not installed; .NET not installed.
- **Recommendation:** Safe for isolated Python venvs (`backtesting.py`, `vectorbt`) with 1 concurrent research worker. Defer `QuantConnect/Lean` (.NET/Docker).
