# -*- coding: utf-8 -*-
"""collectors/nyfed_effr_collector.py - NY Fed EFFR 日频采集器

NY Fed 官方 API 无需密钥。拉取 EFFR（有效联邦基金利率）日频数据，
按月取平均，写入 FEDFUNDS_NYFED（与 FRED 的 FEDFUNDS 月均定义完全一致）。
"""
import requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
try:
    from .base_collector import BaseCollector
except ImportError:
    from base_collector import BaseCollector


class NYFedEFFRCollector(BaseCollector):
    BASE_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/250.json"

    def __init__(self):
        super().__init__(name='nyfed_effr', rate_limit_per_min=20)

    def fetch(self, indicator, **kwargs):
        """
        indicator 固定是 FEDFUNDS_NYFED。
        返回 [(YYYY-MM-01, 当月EFFR均值), ...]，只保留完整月份。
        """
        r = requests.get(self.BASE_URL, timeout=20)
        r.raise_for_status()
        data = r.json()

        ref_rates = data.get('refRates', [])
        if not ref_rates:
            return []

        # 按月份分组
        monthly = {}
        for item in ref_rates:
            dt_str = item.get('effectiveDate')
            rate = item.get('percentRate')
            if not dt_str or rate is None:
                continue
            try:
                dt = datetime.strptime(dt_str, '%Y-%m-%d')
                rate = float(rate)
            except (ValueError, TypeError):
                continue
            month_key = dt.strftime('%Y-%m-01')
            monthly.setdefault(month_key, []).append(rate)

        # 计算月均，剔除当月未完整的月份
        today = datetime.now()
        current_month = today.strftime('%Y-%m-01')
        rows = []
        for month, rates in monthly.items():
            if month == current_month:
                continue  # 当月不完整，跳过
            rows.append((month, sum(rates) / len(rates)))

        return sorted(rows)


def main():
    c = NYFedEFFRCollector()
    c.run_one('FEDFUNDS_NYFED')


if __name__ == "__main__":
    main()