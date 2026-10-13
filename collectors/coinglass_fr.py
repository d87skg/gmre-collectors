# -*- coding: utf-8 -*-
"""coinglass_fr.py - CoinGlass FR/OI/清算聚合采集"""
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# CoinGlass 公开接口（可能需 API key，可能已变更）
URLS = {
    "funding": "https://open-api.coinglass.com/public/v2/indicator/funding_rate_ex",
    "oi": "https://open-api.coinglass.com/public/v2/indicator/open_interest_ex",
    "liquidation": "https://open-api.coinglass.com/public/v2/indicator/liquidation_ex",
}

HEADERS = {
    "accept": "application/json",
    "User-Agent": "Mozilla/5.0",
}


def fetch(url):
    """请求 CoinGlass API"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            return r.json()
        print(f"  [fail] status={r.status_code}")
        return None
    except Exception as e:
        print(f"  [error] {e}")
        return None


def parse_items(items):
    """解析 CoinGlass 返回的 data 字段"""
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append({
            "symbol": item.get("symbol"),
            "exchange": item.get("exchangeName") or item.get("exchange"),
            "funding_rate": item.get("rate") or item.get("fundingRate"),
            "oi_usd": item.get("openInterest") or item.get("openInterestValue"),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def main():
    results = {}
    for name, url in URLS.items():
        print(f"\n[fetch] {name}")
        data = fetch(url)
        if not data:
            print(f"  [skip] {name}")
            continue

        items = data.get("data", []) if isinstance(data, dict) else []
        if not items:
            print(f"  [empty] {name}")
            continue

        rows = parse_items(items)
        if rows:
            out = DATA_DIR / f"coinglass_{name}.csv"
            pd.DataFrame(rows).to_csv(out, index=False)
            print(f"  [ok] {len(rows)} rows -> {out}")
            results[name] = len(rows)

    if not results:
        print("\n[!] CoinGlass 全部失败：")
        print("    - 可能需要 API key")
        print("    - 或接口路径已变更")
        print("    - 建议 10-21 后评估是否需要付费 API")
    else:
        print(f"\n[summary] 成功 {len(results)}/3：{list(results.keys())}")


if __name__ == "__main__":
    main()