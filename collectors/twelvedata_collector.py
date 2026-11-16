# -*- coding: utf-8 -*-
"""collectors/twelvedata_collector.py - Twelve Data 免费层采集器"""
import os
import requests
from dotenv import load_dotenv

try:
    from .base_collector import BaseCollector
except ImportError:
    from base_collector import BaseCollector

load_dotenv(r'D:\HGZC\.env')


class TwelveDataCollector(BaseCollector):
    BASE_URL = "https://api.twelvedata.com/time_series"

    def __init__(self):
        super().__init__(name='twelvedata', rate_limit_per_min=8)
        self.api_key = os.environ.get('TD_API_KEY', '').strip()

    def fetch(self, symbol, interval='1day', outputsize=365, **kwargs):
        if not self.api_key:
            raise RuntimeError("缺少 TD_API_KEY，请在 .env 中配置")
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": self.api_key,
        }
        r = requests.get(self.BASE_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        if data.get('status') == 'error' or 'values' not in data:
            raise RuntimeError(f"Twelve Data 返回错误: {data.get('message')}")

        rows = []
        for item in data['values']:
            dt = str(item['datetime'])[:10]
            try:
                rows.append((dt, float(item['close'])))
            except (KeyError, ValueError):
                continue
        return sorted(rows)


def main():
    c = TwelveDataCollector()
    if not c.api_key:
        print("⚠️ 未配置 TD_API_KEY，跳过测试")
        return
    c.run_one('WTI_OIL_TD', symbol='WTI')
    c.run_one('GOLD_PRICE_TD', symbol='XAU/USD')


if __name__ == "__main__":
    main()