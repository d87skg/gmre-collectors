# -*- coding: utf-8 -*-
"""hyperliquid_mids.py - Hyperliquid 链上标记价采集"""
import requests
import pandas as pd
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).parent.parent / "data" / "lti"
DATA_DIR.mkdir(parents=True, exist_ok=True)

URL = "https://api.hyperliquid.xyz/info"
TARGET_COINS = ["BTC", "ETH", "SOL"]


def fetch_all_mids():
    """REST allMids - 所有资产的中间价"""
    r = requests.post(URL, json={"type": "allMids"}, timeout=10)
    r.raise_for_status()
    return r.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=60, help="采集时长（秒）")
    parser.add_argument("--interval", type=float, default=2.0, help="轮询间隔（秒）")
    args = parser.parse_args()

    print(f"[start] Hyperliquid allMids 采集 {args.duration}s, 间隔 {args.interval}s")
    rows = []
    t0 = time.time()

    while time.time() - t0 < args.duration:
        try:
            mids = fetch_all_mids()
            ts = datetime.now(timezone.utc).isoformat()
            for coin in TARGET_COINS:
                if coin in mids:
                    rows.append({
                        "timestamp": ts,
                        "coin": coin,
                        "mark_price": float(mids[coin]),
                        "source": "hyperliquid_allMids",
                        "data_type": "observed",
                    })
            print(f"[{int(time.time()-t0):3d}s] BTC={mids.get('BTC','?')} ETH={mids.get('ETH','?')} SOL={mids.get('SOL','?')}")
        except Exception as e:
            print(f"[error] {e}")
        time.sleep(args.interval)

    df = pd.DataFrame(rows)
    out = DATA_DIR / "hyperliquid_mids.csv"
    df.to_csv(out, index=False)
    print(f"\n[saved] {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()