# -*- coding: utf-8 -*-
"""bybit_perp.py - Bybit 永续 FR/OI"""
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"

def fetch_bybit(symbol="BTCUSDT"):
    url = "https://api.bybit.com/v5/market/tickers"
    r = requests.get(url, params={"category": "linear", "symbol": symbol}, timeout=30)
    r.raise_for_status()
    data = r.json().get("result", {}).get("list", [])
    if not data:
        return None
    item = data[0]
    return {
        "symbol": symbol,
        "funding_rate": float(item.get("fundingRate", 0)),
        "open_interest": float(item.get("openInterest", 0)),
        "oi_usd": float(item.get("openInterestValue", 0)),
        "retrieved_at": datetime.utcnow().isoformat(),
    }

def main():
    rows = []
    for sym in ["BTCUSDT", "ETHUSDT"]:
        try:
            d = fetch_bybit(sym)
            if d:
                rows.append(d)
                print(f"[ok] {sym}")
        except Exception as e:
            print(f"[fail] {sym}: {e}")
    out = DATA_DIR / "bybit_perp.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"saved: {out}")

if __name__ == "__main__":
    main()