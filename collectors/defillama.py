"""DeFiLlama Collector (onchain / DeFi 系统层, 无需 key)。
TVL / Stablecoin 供给 / DEX 成交量。"""
import logging
from datetime import datetime
from typing import List

from core.normalizer import finalize_observation
from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)


class DeFiLlamaCollector(BaseCollector):
    source_id = "defillama"
    BASE = "https://api.llama.fi"

    def fetch(self) -> List[Observation]:
        out: List[Observation] = []
        ts = datetime.now().replace(second=0, microsecond=0)

        # --- 全链 TVL ---
        try:
            chains = self.client.get(f"{self.BASE}/v2/chains", timeout=45)
            total_tvl = sum(float(c.get("tvl") or 0.0) for c in chains)
            out.append(finalize_observation(
                "defillama", "LLAMA_TVL_TOTAL", ts, total_tvl,
                unit="usd", frequency="daily", category="onchain"))
        except Exception as e:  # noqa: BLE001
            logger.warning("[defillama] chains failed: %s", e)

        # --- Stablecoin 总供给 ---
        try:
            stables = self.client.get(
                "https://stablecoins.llama.fi/stablecoins?includePrices=false",
                timeout=45)
            assets = stables.get("peggedAssets", [])
            total = sum(
                float(a.get("circulating", {}).get("peggedUSD") or 0.0)
                for a in assets
            )
            out.append(finalize_observation(
                "defillama", "LLAMA_STABLECOINS", ts, total,
                unit="usd", frequency="daily", category="onchain"))
        except Exception as e:  # noqa: BLE001
            logger.warning("[defillama] stablecoins failed: %s", e)

        # --- DEX 日成交量 ---
        try:
            dex = self.client.get(
                f"{self.BASE}/overview/dexs",
                params={"dataType": "dailyVolume",
                        "excludeTotalDataChart": "true",
                        "excludeTotalDataChartBreakdown": "true"},
                timeout=45)
            vol = dex.get("totalVolume")
            if vol:
                out.append(finalize_observation(
                    "defillama", "LLAMA_DEX_VOL", ts, float(vol),
                    unit="usd", frequency="daily", category="onchain"))
        except Exception as e:  # noqa: BLE001
            logger.warning("[defillama] dex volume failed: %s", e)

        return out
