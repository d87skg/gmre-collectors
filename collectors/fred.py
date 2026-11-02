"""FRED Collector (需要 FRED_API_KEY)。支持 vintage/ALFRED 预留。"""
import logging
from datetime import datetime
from typing import List, Optional

from core.normalizer import finalize_observation
from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)

FRED_SERIES = [
    "FEDFUNDS", "SOFR", "DGS2", "DGS10", "DGS30", "T10Y2Y", "T10YIE",
    "CPIAUCSL", "CPILFESL", "PCEPI", "UNRATE", "PAYEMS", "M2SL",
    "WALCL", "RRPONTSYD", "DTWEXBGS", "BAMLH0A0HYM2", "BAMLC0A0CM",
]


class FREDCollector(BaseCollector):
    source_id = "fred"
    BASE = "https://api.stlouisfed.org/fred"

    def available(self) -> bool:
        return bool(self.env.get("FRED_API_KEY"))

    def fetch(self, series_ids: Optional[List[str]] = None,
              realtime_start: str = "1900-01-01") -> List[Observation]:
        key = self.env["FRED_API_KEY"]
        out: List[Observation] = []
        for sid in (series_ids or FRED_SERIES):
            params = {
                "series_id": sid, "api_key": key, "file_type": "json",
                "sort_order": "desc", "limit": "750",
                "realtime_start": realtime_start,  # ALFRED vintage 预留
            }
            try:
                data = self.client.get(f"{self.BASE}/series/observations", params=params)
            except Exception as e:  # noqa: BLE001
                logger.warning("[fred] series %s failed: %s", sid, e)
                continue
            for x in data.get("observations", []):
                if x.get("value") in (None, "", "."):
                    continue
                try:
                    ts = datetime.fromisoformat(x["date"])
                    val = float(x["value"])
                except (ValueError, KeyError):
                    continue
                out.append(finalize_observation(
                    "fred", sid, ts, val,
                    unit="%", frequency="daily",
                    category="macro",
                ))
        return out
