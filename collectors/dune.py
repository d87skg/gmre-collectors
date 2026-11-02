"""Dune Collector (onchain, 需要 DUNE_API_KEY)。
正确用法: Dune 上建 Saved Query -> 拿 query_id -> 本类按 query_id 拉结果,
不要在 Python 里写死 SQL。无 key 时跳过。
"""
import logging
from datetime import datetime
from typing import List

from core.normalizer import finalize_observation
from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)

# 预留: 需要用户在 Dune 创建查询后填入 query_id
DUNE_QUERIES = {
    # "stablecoin_net_flow": 1234567,
}


class DuneCollector(BaseCollector):
    source_id = "dune"
    BASE = "https://api.dune.com/api/v1"

    def available(self) -> bool:
        return bool(self.env.get("DUNE_API_KEY"))

    def execute(self, query_id: int) -> dict:
        headers = {"X-Dune-API-Key": self.env["DUNE_API_KEY"]}
        url = f"{self.BASE}/query/{query_id}/results"
        return self.client.get(url, headers=headers, timeout=60)

    def fetch(self) -> List[Observation]:
        out: List[Observation] = []
        if not DUNE_QUERIES:
            logger.warning("[dune] 未配置 DUNE_QUERIES (需先创建 Saved Query)")
            return out
        for name, query_id in DUNE_QUERIES.items():
            try:
                res = self.execute(query_id)
                rows = res.get("result", {}).get("rows", [])
                for row in rows:
                    val = row.get("value")
                    if val is None:
                        continue
                    ts = datetime.now().replace(second=0, microsecond=0)
                    out.append(finalize_observation(
                        "dune", f"DUNE_{name.upper()}", ts, float(val),
                        unit="usd", frequency="daily", category="onchain"))
            except Exception as e:  # noqa: BLE001
                logger.warning("[dune] query %s failed: %s", name, e)
        return out
