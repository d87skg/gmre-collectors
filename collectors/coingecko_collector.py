# -*- coding: utf-8 -*-
"""collectors/coingecko_collector.py - CoinGecko 免费 API 采集器（v2）"""
import requests
from datetime import datetime, timezone

try:
    from .base_collector import BaseCollector
except ImportError:
    from base_collector import BaseCollector


class CoinGeckoCollector(BaseCollector):
    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self):
        super().__init__(name='coingecko', rate_limit_per_min=25)

    def fetch(self, indicator, coin_id=None, days=365, **kwargs):
        """indicator 是 series_id（如 BTC_SPOT_PRICE_1H_CG），coin_id 是 CoinGecko 的币种 ID"""
        if not coin_id:
            raise ValueError(f"缺少 coin_id 参数，indicator={indicator}")

        url = f"{self.BASE_URL}/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": days, "interval": "daily"}
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        rows = []
        for ts_ms, price in data.get('prices', []):
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            rows.append((dt, float(price)))

        seen = {}
        for dt, v in rows:
            seen[dt] = v
        return sorted(seen.items())


def main():
    c = CoinGeckoCollector()
    c.run_one('BTC_SPOT_PRICE_1H_CG', coin_id='bitcoin', days=90)
    c.run_one('ETH_PRICE_CG', coin_id='ethereum', days=90)


if __name__ == "__main__":
    main()