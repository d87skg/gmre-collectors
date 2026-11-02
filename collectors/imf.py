"""IMF Collector (SDMX IFS, 无需 key)。容错 + 可配置; 默认链路不强制。"""
import logging
from typing import List

from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)


class IMFCollector(BaseCollector):
    source_id = "imf"
    BASE = "https://sdmxcentral.imf.org/ws/public/sdmxapi/rest"

    def fetch(self) -> List[Observation]:
        # 预留: IFS 数据流 (如 M.US.NGDP_RPCH...)。端点按需配置后启用。
        return []
