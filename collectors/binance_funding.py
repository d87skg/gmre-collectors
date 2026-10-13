# -*- coding: utf-8 -*-
"""binance_funding.py - Binance 永续资金费率"""
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def fetch(symbol="BTCUSDT"):
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    r = requests.get(url, params={"symbol": symbol}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return {
        "symbol": d.get("symbol"),
        "mark_price": float(d.get("markPrice", 0)),
        "index_price": float(d.get("indexPrice", 0)),
        "funding_rate": float(d.get("lastFundingRate", 0)),
        "next_funding_time": d.get("nextFundingTime"),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    rows = []
    for sym in ["BTCUSDT", "ETHUSDT"]:
        try:
            rows.append(fetch(sym))
            print(f"[ok] {sym}")
        except Exception as e:
            print(f"[fail] {sym}: {e}")
    if rows:
        out = DATA_DIR / "binance_funding.csv"
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"saved: {out}")


if __name__ == "__main__":
    main()