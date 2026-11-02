"""Collector 基类与注册表。每个 collector 实现 fetch() -> List[Observation]。
无 key / 端点不可用时返回 [] 并告警, 保证主链路不中断。"""
import logging
import os
from typing import Dict, List, Optional

from core.http_client import APIClient
from core.schema import Observation

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BaseCollector:
    source_id: str = "base"

    def __init__(self, client: Optional[APIClient] = None, env: Optional[Dict[str, str]] = None):
        self.client = client or APIClient()
        self.env = env or {}

    def available(self) -> bool:
        return True

    def fetch(self) -> List[Observation]:
        raise NotImplementedError

    def _safe_fetch(self) -> List[Observation]:
        try:
            if not self.available():
                logger.warning("[%s] skipped: unavailable (missing key?)", self.source_id)
                return []
            obs = self.fetch()
            logger.info("[%s] collected %d observations", self.source_id, len(obs))
            return obs
        except Exception as e:  # noqa: BLE001 — collector 级容错
            logger.warning("[%s] fetch failed: %s", self.source_id, e)
            return []

    @staticmethod
    def _env_from_dotenv() -> Dict[str, str]:
        """轻量 .env 读取 (不强制依赖 python-dotenv)。"""
        env: Dict[str, str] = {}
        dotenv = os.path.join(BASE_DIR, ".env")
        if os.path.exists(dotenv):
            with open(dotenv, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
        for k, v in os.environ.items():
            env.setdefault(k, v)
        return env


# 延迟导入, 避免循环依赖
def get_collector(source_id: str) -> BaseCollector:
    from . import (alphavantage, bis, coingecko, defillama, dune, ecb, fred,
                   imf, market, sec, treasury, worldbank)
    registry = {
        "fred": fred.FREDCollector,
        "treasury": treasury.TreasuryCollector,
        "ecb": ecb.ECBCollector,
        "bis": bis.BISCollector,
        "imf": imf.IMFCollector,
        "worldbank": worldbank.WorldBankCollector,
        "market": market.MarketCollector,
        "sec": sec.SECCollector,
        "alphavantage": alphavantage.AlphaVantageCollector,
        "coingecko": coingecko.CoinGeckoCollector,
        "defillama": defillama.DeFiLlamaCollector,
        "dune": dune.DuneCollector,
    }
    cls = registry[source_id]
    return cls(env=BaseCollector._env_from_dotenv())


ALL_SOURCES = [
    "fred", "treasury", "ecb", "bis", "imf", "worldbank", "market",
    "sec", "alphavantage", "coingecko", "defillama", "dune",
]
