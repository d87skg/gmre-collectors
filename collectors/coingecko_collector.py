# -*- coding: utf-8 -*-
"""collectors/coingecko_collector.py - CoinGecko 采集器（v4: 超时修复 + CryptoCompare 兜底）"""
import requests
import time
from datetime import datetime, timezone, timedelta

try:
    from .base_collector import BaseCollector
except ImportError:
    from base_collector import BaseCollector


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
}


class CoinGeckoCollector(BaseCollector):
    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self):
        super().__init__(name='coingecko', rate_limit_per_min=20, retries=2)

    def _fetch_coingecko(self, coin_id, days):
        url = f"{self.BASE_URL}/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": days, "interval": "daily"}
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        rows = []
        for ts_ms, price in data.get('prices', []):
            dt = (datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                  - timedelta(days=1)).strftime('%Y-%m-%d')
            rows.append((dt, float(price)))
        return rows

    def _fetch_cryptocompare(self, coin_symbol, days):
        """CryptoCompare 兜底（国内通常可直连）"""
        url = "https://min-api.cryptocompare.com/data/v2/histoday"
        params = {"fsym": coin_symbol, "tsym": "USD", "limit": days}
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get('Response') != 'Success':
            raise RuntimeError(f"CryptoCompare 返回错误: {data.get('Message')}")
        rows = []
        for item in data.get('Data', {}).get('Data', []):
            dt = datetime.fromtimestamp(item['time'], tz=timezone.utc).strftime('%Y-%m-%d')
            rows.append((dt, float(item['close'])))
        return rows

    def fetch(self, indicator, coin_id=None, symbol=None, days=90, **kwargs):
        if not coin_id:
            raise ValueError(f"缺少 coin_id 参数，indicator={indicator}")

        # 第一优先：CoinGecko
        try:
            rows = self._fetch_coingecko(coin_id, days)
            if rows:
                print(f"    [{indicator}] CoinGecko 成功，{len(rows)} 条")
                return self._dedup(rows)
        except Exception as e:
            print(f"    [{indicator}] CoinGecko 失败: {str(e)[:80]}")
            time.sleep(2)

        # 第二优先：CryptoCompare
        if symbol:
            try:
                rows = self._fetch_cryptocompare(symbol, days)
                if rows:
                    print(f"    [{indicator}] 已切换到 CryptoCompare，{len(rows)} 条")
                    return self._dedup(rows)
            except Exception as e:
                print(f"    [{indicator}] CryptoCompare 也失败: {str(e)[:80]}")

        raise RuntimeError("所有数据源均失败")

    @staticmethod
    def _dedup(rows):
        seen = {}
        for dt, v in rows:
            seen[dt] = v
        return sorted(seen.items())


def main():
    c = CoinGeckoCollector()
    c.run_one('BTC_SPOT_PRICE_1H_CG', coin_id='bitcoin', symbol='BTC', days=90)
    c.run_one('ETH_PRICE_CG', coin_id='ethereum', symbol='ETH', days=90)


if __name__ == "__main__":
    main()