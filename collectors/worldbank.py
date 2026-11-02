"""World Bank Collector (无需 key): 美国 GDP 增速 / CPI 通胀。"""
import logging
from datetime import datetime
from typing import List

from core.normalizer import finalize_observation
from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)

INDICATORS = [
    ("NY.GDP.MKTP.KD.ZG", "WB_GDP_GROWTH", "growth"),
    ("FP.CPI.TOTL.ZG", "WB_INFLATION", "inflation"),
]


class WorldBankCollector(BaseCollector):
    source_id = "worldbank"
    BASE = "https://api.worldbank.org/v2/country/USA/indicator"

    def fetch(self) -> List[Observation]:
        out: List[Observation] = []
        for ind, sid, category in INDICATORS:
            try:
                data = self.client.get(
                    f"{self.BASE}/{ind}",
                    params={"format": "json", "per_page": "10"},
                )
                rows = data[1] if isinstance(data, list) and len(data) > 1 else []
                for row in rows:
                    if row.get("value") is None:
                        continue
                    ts = datetime(int(row["date"]), 12, 31)
                    out.append(finalize_observation(
                        "worldbank", sid, ts, float(row["value"]),
                        unit="%", frequency="annual", category=category))
            except Exception as e:  # noqa: BLE001
                logger.warning("[worldbank] %s failed: %s", ind, e)
        return out
