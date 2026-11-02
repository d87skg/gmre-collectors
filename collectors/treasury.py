"""US Treasury Collector (官方, 无需 key)。
- TGA_NET_FLOW: DTS 每日净流量 = Withdrawals - Deposits (正=财政部花钱=流动性注入)
- DEBT_TOTAL: 总公共债务 (v2)
端点 2026 年已调整: 旧 operating_cash_balance / dts_table_N 已下线。
"""
import logging
from collections import defaultdict
from datetime import datetime
from typing import List

from core.normalizer import finalize_observation
from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)

DTS_URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
           "v1/accounting/dts/deposits_withdrawals_operating_cash")
DEBT_URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
            "v2/accounting/od/debt_to_penny")


class TreasuryCollector(BaseCollector):
    source_id = "treasury"

    def fetch(self) -> List[Observation]:
        out: List[Observation] = []

        # --- TGA 每日净流量 ---
        try:
            data = self.client.get(
                DTS_URL,
                params={"sort": "-record_date", "page[size]": "500"},
            )
            # DTS 金额单位为百万美元 (millions)
            net_by_day: dict = defaultdict(float)
            for row in data.get("data", []):
                amt_raw = row.get("transaction_today_amt")
                if amt_raw in (None, ""):
                    continue
                ttype = (row.get("transaction_type") or "").lower()
                amt = float(amt_raw) * 1e6  # -> 美元
                day = row["record_date"]
                if "deposit" in ttype:
                    net_by_day[day] -= amt
                else:
                    net_by_day[day] += amt
            for day, net in sorted(net_by_day.items()):
                ts = datetime.fromisoformat(day)
                out.append(finalize_observation(
                    "treasury", "TGA_NET_FLOW", ts, net,
                    unit="usd", frequency="daily", category="liquidity"))
        except Exception as e:  # noqa: BLE001
            logger.warning("[treasury] TGA flow failed: %s", e)

        # --- 总公共债务 (v2) ---
        try:
            data = self.client.get(
                DEBT_URL, params={"sort": "-record_date", "page[size]": "10"})
            for row in data.get("data", []):
                val_raw = row.get("tot_pub_debt_out_amt")
                if val_raw in (None, ""):
                    continue
                ts = datetime.fromisoformat(row["record_date"])
                out.append(finalize_observation(
                    "treasury", "DEBT_TOTAL", ts, float(val_raw),
                    unit="usd", frequency="daily", category="fiscal"))
        except Exception as e:  # noqa: BLE001
            logger.warning("[treasury] debt failed: %s", e)

        return out
