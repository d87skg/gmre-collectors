# -*- coding: utf-8 -*-
"""collectors/bis_collector.py - BIS SDMX API 采集器（v2: 尽力而为，不抛异常）"""
import requests
import csv
import io

try:
    from .base_collector import BaseCollector
except ImportError:
    from base_collector import BaseCollector


class BISCollector(BaseCollector):
    BASE_URL = "https://stats.bis.org/api/v1/data"

    def __init__(self):
        super().__init__(name='bis', rate_limit_per_min=30)

    def _fetch_sdmx_csv(self, flow, key, start_period='2024-01-01'):
        url = f"{self.BASE_URL}/{flow}/{key}"
        params = {"startPeriod": start_period, "format": "csv"}
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        text = r.text
        if not text or ',' not in text:
            return []

        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for row in reader:
            dt_raw = row.get('TIME_PERIOD') or row.get('TIME') or ''
            val_raw = row.get('OBS_VALUE') or ''
            dt = self._normalize_date(dt_raw)
            if not dt or not val_raw:
                continue
            try:
                rows.append((dt, float(val_raw)))
            except ValueError:
                continue

        seen = {}
        for dt, v in rows:
            seen[dt] = v
        return sorted(seen.items())

    @staticmethod
    def _normalize_date(s):
        s = str(s).strip()
        if not s:
            return None
        if len(s) == 10:
            return s
        if len(s) == 7:
            return f"{s}-01"
        if len(s) == 4:
            return f"{s}-01-01"
        return None

    def fetch(self, indicator, **kwargs):
        mapping = {
            'FEDFUNDS_BIS':  ('BIS,WS_CBPOL,1.0', 'D.US'),
            'ECB_RATE_BIS':  ('BIS,WS_CBPOL,1.0', 'D.XM'),
            'BOJ_RATE_BIS':  ('BIS,WS_CBPOL,1.0', 'D.JP'),
            'GBP_RATE_BIS':  ('BIS,WS_CBPOL,1.0', 'D.GB'),
        }
        if indicator not in mapping:
            raise ValueError(f"BIS 采集器不支持指标: {indicator}（DXY 已暂时禁用）")

        flow, key = mapping[indicator]
        return self._fetch_sdmx_csv(flow, key, start_period='2024-01-01')


def main():
    c = BISCollector()
    for ind in ['FEDFUNDS_BIS']:
        try:
            c.run_one(ind)
        except Exception as e:
            print(f"  ⚠️ {ind} 拉取失败，不影响主流程: {e}")


if __name__ == "__main__":
    main()