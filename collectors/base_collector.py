# -*- coding: utf-8 -*-
"""collectors/base_collector.py - 所有外部数据采集器的基类（v2: 修复 generated column）"""
import time
import sqlite3
import os
from abc import ABC, abstractmethod
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get('GMRE_DB_PATH', os.path.join(BASE_DIR, 'data', 'macro.db'))


class BaseCollector(ABC):
    def __init__(self, name, rate_limit_per_min=60, retries=3):
        self.name = name
        self.min_interval = 60.0 / max(rate_limit_per_min, 1)
        self.retries = retries
        self._last_call = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.time()

    @abstractmethod
    def fetch(self, indicator, **kwargs):
        """返回 [(date_str 'YYYY-MM-DD', value float), ...]"""
        pass

    def _save(self, series_id, rows, source_tag, unit_hint=None):
        """统一写入 observations 表（使用 obs_ts + obs_date，避开 generated column）"""
        if not rows:
            print(f"  ⏭️  {self.name} -> {series_id}: 无新数据")
            return 0

        conn = sqlite3.connect(DB_PATH)
        inserted = 0
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            for dt, val in rows:
                if val is None:
                    continue
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO observations "
                        "(series_id, obs_ts, obs_date, ingest_at, value, source, unit) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (series_id, dt, dt, now_str, float(val), source_tag, unit_hint)
                    )
                    inserted += 1
                except sqlite3.Error as e:
                    print(f"  ⚠️ {self.name} -> {series_id} 入库失败: {e}")
                    break
            conn.commit()
            print(f"  ✅ {self.name} -> {series_id}: 新增 {inserted} 行 (source={source_tag})")
            return inserted
        finally:
            conn.close()

    def run_one(self, indicator, **kwargs):
        for attempt in range(1, self.retries + 1):
            try:
                self._throttle()
                rows = self.fetch(indicator, **kwargs)
                if rows:
                    self._save(indicator, rows, source_tag=self.name)
                return rows
            except Exception as e:
                if attempt == self.retries:
                    print(f"  ❌ {self.name} -> {indicator} 失败（已重试 {attempt} 次）: {e}")
                    return []
                time.sleep(2 ** attempt)