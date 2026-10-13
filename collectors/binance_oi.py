# -*- coding: utf-8 -*-
"""binance_oi.py - Binance 未平仓合约"""
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"

def fetch_binance_oi(symbol="BTCUSDT"):
    url = "https://fapi.binance.com/fapi/v1/openInterest"
    r = requests.get(url, params={"symbol": symbol}, timeout=30)
    r.raise_for_status()
    data = r.json()
    return {
        "symbol": data.get("symbol"),
        "open_interest": float(data.get("openInterest", 0)),
        "retrieved_at": datetime.utcnow().isoformat(),
    }

def main():
    rows = []
    for sym in ["BTCUSDT", "ETHUSDT"]:
        try:
            rows.append(fetch_binance_oi(sym))
            print(f"[ok] {sym}")
        except Exception as e:
            print(f"[fail] {sym}: {e}")
    out = DATA_DIR / "binance_oi.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"saved: {out}")

if __name__ == "__main__":
    main()