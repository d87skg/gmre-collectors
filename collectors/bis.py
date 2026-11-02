"""BIS Collector (SDMX REST, 无需 key)。
BIS Webstats API v2: https://stats.bis.org/api/v2/data/...
端点结构随 dataflow 变化, 这里提供可配置 dataflow + 容错。
默认演示链路不强制拉取; 配置 config/bis_flows.yaml 后可启用。
"""
import logging
from typing import List

from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)


class BISCollector(BaseCollector):
    source_id = "bis"
    BASE = "https://stats.bis.org/api/v2/data"

    # dataflow -> (series_id, frequency, unit); 可按需在 .env 或配置中扩展
    FLOWS = {
        # "WS_CBS/1.0/US.L.BCA.US.Q": ("BIS_CREDIT_GROWTH", "quarterly", "%"),
    }

    def fetch(self) -> List[Observation]:
        out: List[Observation] = []
        for flow, (sid, freq, unit) in self.FLOWS.items():
            try:
                url = f"{self.BASE}/dataflow/{flow}"
                data = self.client.get(url, params={"format": "jsondata"})
                obs = (data.get("data", {}).get("dataSets", [{}])[0]
                       .get("series", {}))
                logger.info("[bis] flow %s series count=%d", flow, len(obs))
            except Exception as e:  # noqa: BLE001
                logger.warning("[bis] flow %s failed: %s (flow 未配置则跳过)", flow, e)
        return out
