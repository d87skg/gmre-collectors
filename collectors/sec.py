"""SEC EDGAR Collector (无需 key, 需要合规 User-Agent)。
抓取公司 10-K 年度 Revenue / NetIncomeLoss (XBRL companyfacts)。
"""
import logging
from datetime import datetime
from typing import Dict, List, Tuple

from core.normalizer import finalize_observation
from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)

COMPANIES = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
}


class SECCollector(BaseCollector):
    source_id = "sec"
    BASE = "https://data.sec.gov"

    def available(self) -> bool:
        return True

    def fetch(self) -> List[Observation]:
        out: List[Observation] = []
        for ticker, cik in COMPANIES.items():
            try:
                url = f"{self.BASE}/api/xbrl/companyfacts/CIK{cik}.json"
                data = self.client.get(
                    url,
                    headers={"User-Agent": "GlobalMacroDataOS research contact@example.com"},
                    timeout=90,
                )
                facts = data.get("facts", {}).get("us-gaap", {})
                for metric, sid in (("Revenue", f"SEC_REV_{ticker}"),
                                    ("NetIncomeLoss", f"SEC_NI_{ticker}")):
                    payload = facts.get(metric, {}).get("units", {}).get("USD", [])
                    annual = [p for p in payload if p.get("form") == "10-K"]
                    if not annual:
                        continue
                    latest = max(annual, key=lambda p: p["end"])
                    end = latest["end"]
                    if not end or end < "2010-01-01":
                        continue
                    ts = datetime(int(end[:4]), int(end[5:7]), int(end[8:10]))
                    out.append(finalize_observation(
                        "sec", sid, ts, float(latest["val"]),
                        unit="usd", frequency="annual", category="equity"))
            except Exception as e:  # noqa: BLE001
                logger.warning("[sec] %s failed: %s", ticker, e)
        return out
