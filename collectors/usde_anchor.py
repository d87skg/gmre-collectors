# -*- coding: utf-8 -*-
"""usde_anchor.py - USDE 锚定监控"""
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).parent.parent / "data" / "lti"
DATA_DIR.mkdir(parents=True, exist_ok=True)

COINGECKO_PRICE = "https://api.coingecko.com/api/v3/simple/price"

def fetch_usde_price():
    params = {
        "ids": "ethena-usde",
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_last_updated_at": "true",
    }
    r = requests.get(COINGECKO_PRICE, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def main():
    try:
        data = fetch_usde_price()
        usde = data.get("ethena-usde", {})
        price = usde.get("usd")
        change = usde.get("usd_24h_change")

        if price is None:
            print("[fail] CoinGecko 未返回 USDE 价格")
            return

        deviation_bp = (price - 1.0) * 10000

        if abs(deviation_bp) < 10:
            status = "NORMAL"
        elif abs(deviation_bp) < 30:
            status = "WARNING"
        elif abs(deviation_bp) < 100:
            status = "ALERT"
        else:
            status = "DEPEG"

        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "usde_price": price,
            "deviation_bp": round(deviation_bp, 2),
            "change_24h_pct": change,
            "status": status,
            "source": "coingecko",
            "data_type": "observed",
        }

        out = DATA_DIR / "usde_anchor.csv"
        df_new = pd.DataFrame([row])
        if out.exists():
            df_old = pd.read_csv(out)
            df = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df = df_new
        df.to_csv(out, index=False)

        print(f"[ok] USDE = ${price:.4f}")
        print(f"[deviation] {deviation_bp:+.2f} bp ({status})")
        print(f"[24h] {change:+.2f}%")
        print(f"[saved] {out}")

    except Exception as e:
        print(f"[error] {e}")

if __name__ == "__main__":
    main()