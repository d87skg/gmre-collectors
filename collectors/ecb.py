"""ECB Collector: SDMX 参考汇率 (EURUSD)。sdw 域名不通时用 Frankfurter (ECB 数据) 兜底。"""
import csv
import io
import logging
from datetime import datetime
from typing import List

from core.normalizer import finalize_observation
from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)


class ECBCollector(BaseCollector):
    source_id = "ecb"
    SDW = "https://sdw-wsrest.ecb.europa.eu/service/data"
    DATA_API = "https://data-api.ecb.europa.eu/service/data"
    FRANKFURTER = "https://api.frankfurter.app/latest"

    def _fetch_sdmx_csv(self, base: str) -> List[Observation]:
        url = f"{base}/EXR/D.USD.EUR.SP00.A"
        text = self.client.get_text(
            url, params={"format": "csvdata", "lastNObservations": "10"},
            timeout=20)
        reader = csv.DictReader(io.StringIO(text))
        out: List[Observation] = []
        for row in reader:
            time_period = row.get("TIME_PERIOD")
            value = row.get("OBS_VALUE")
            if not time_period or value in (None, ""):
                continue
            try:
                ts = datetime.fromisoformat(time_period)
                val = float(value)
            except (ValueError, TypeError):
                continue
            out.append(finalize_observation(
                "ecb", "ECB_EURUSD", ts, val,
                unit="fx", frequency="annual", category="usd"))
        return out

    def _fetch_frankfurter(self) -> List[Observation]:
        data = self.client.get(self.FRANKFURTER,
                               params={"from": "USD", "to": "EUR"}, timeout=20)
        rate = data.get("rates", {}).get("EUR")
        date = data.get("date")
        if rate and date:
            eurusd = 1.0 / float(rate)
            ts = datetime.fromisoformat(date)
            return [finalize_observation(
                "ecb", "ECB_EURUSD", ts, eurusd,
                unit="fx", frequency="daily", category="usd")]
        return []

    def fetch(self) -> List[Observation]:
        for base in (self.SDW, self.DATA_API):
            try:
                obs = self._fetch_sdmx_csv(base)
                if obs:
                    return obs
            except Exception as e:  # noqa: BLE001
                logger.warning("[ecb] %s failed: %s", base.split("/")[2], e)
        try:
            return self._fetch_frankfurter()
        except Exception as e:  # noqa: BLE001
            logger.warning("[ecb] frankfurter fallback failed: %s", e)
            return []
