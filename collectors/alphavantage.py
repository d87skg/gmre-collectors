"""Alpha Vantage Collector (需要 key; 免费 25 req/day)。
仅作为低频辅助; Scheduler 必须限制每日调用次数。
"""
import logging
from datetime import datetime
from typing import List

from core.normalizer import finalize_observation
from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)


class AlphaVantageCollector(BaseCollector):
    source_id = "alphavantage"
    BASE = "https://www.alphavantage.co/query"

    def available(self) -> bool:
        return bool(self.env.get("ALPHAVANTAGE_API_KEY"))

    def fetch(self) -> List[Observation]:
        key = self.env["ALPHAVANTAGE_API_KEY"]
        out: List[Observation] = []
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": "SPY",
            "apikey": key,
            "outputsize": "compact",
        }
        try:
            data = self.client.get(self.BASE, params=params)
            series = data.get("Time Series (Daily)", {})
            for day, vals in sorted(series.items()):
                ts = datetime.fromisoformat(day)
                out.append(finalize_observation(
                    "alphavantage", "AV_SPX_CLOSE", ts, float(vals["4. close"]),
                    unit="usd", frequency="daily", category="market"))
        except Exception as e:  # noqa: BLE001
            logger.warning("[alphavantage] failed: %s", e)
        return out
