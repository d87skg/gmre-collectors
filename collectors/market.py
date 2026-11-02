"""市场数据 Collector (全部官方/公开, 无需 key):
- 美债收益率曲线: US Treasury 官方 CSV (2Y/5Y/10Y/30Y)
- VIX: CBOE 官方历史 CSV
- DXY 代理: Frankfurter (ECB 数据) 六货币篮子加权计算
- 黄金: gold-api 现货价
"""
import sys as _sys
from pathlib import Path as _Path
_PROJECT_ROOT = _Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))
import logging
import math
import os
from datetime import datetime
from typing import List, Optional

from core.normalizer import finalize_observation
from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)

TREASURY_CSV = ("https://home.treasury.gov/resource-center/data-chart-center/"
                "interest-rates/daily-treasury-rates.csv/2026/all"
                "?type=daily_treasury_yield_curve"
                "&field_tdr_date_value=2026&page&_format=csv")
CBOE_VIX = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
FRANKFURTER = "https://api.frankfurter.app"
GOLD_API = "https://api.gold-api.com/price/XAU"

# DXY 权重 (近似官方): EUR 0.576 JPY 0.136 GBP 0.119 CAD 0.091 SEK 0.042 CHF 0.036
DXY_WEIGHTS = {"EUR": 0.576, "JPY": 0.136, "GBP": 0.119, "CAD": 0.091,
               "SEK": 0.042, "CHF": 0.036}
DXY_CONST = 50.14348112


class MarketCollector(BaseCollector):
    source_id = "market"

    # ---------- 美债收益率 ----------
    def _fetch_yields(self) -> List[Observation]:
        out: List[Observation] = []
        text = self.client.get_text(TREASURY_CSV, timeout=30)
        lines = [ln for ln in text.strip().splitlines() if ln]
        if not lines:
            return out
        header = [h.strip().strip('"') for h in lines[0].split(",")]
        col_map = {"2 Yr": "YC2Y", "5 Yr": "YC5Y",
                   "10 Yr": "YC10Y", "30 Yr": "YC30Y"}
        for ln in lines[1:]:
            cells = [c.strip().strip('"') for c in ln.split(",")]
            if len(cells) < len(header):
                continue
            try:
                ts = datetime.strptime(cells[0], "%m/%d/%Y")
            except ValueError:
                continue
            for i, col in enumerate(header):
                sid = col_map.get(col)
                if not sid:
                    continue
                raw = cells[i] if i < len(cells) else ""
                if raw in ("", "N/A", "."):
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    continue
                out.append(finalize_observation(
                    "market", sid, ts, val,
                    unit="%", frequency="daily", category="rates"))
        return out

    # ---------- CBOE VIX ----------
    def _fetch_vix(self) -> List[Observation]:
        out: List[Observation] = []
        text = self.client.get_text(CBOE_VIX, timeout=30)
        lines = [ln for ln in text.strip().splitlines() if ln]
        if not lines:
            return out
        for ln in lines[1:]:
            cells = ln.split(",")
            if len(cells) < 5:
                continue
            try:
                ts = datetime.strptime(cells[0], "%m/%d/%Y")
                close = float(cells[4])
            except (ValueError, IndexError):
                continue
            out.append(finalize_observation(
                "market", "VIX", ts, close,
                unit="idx", frequency="daily", category="risk"))
        return out

    # ---------- DXY 代理 (Frankfurter 篮子) ----------
    def _fetch_dxy(self) -> List[Observation]:
        out: List[Observation] = []
        try:
            # 最近 3 个月日度汇率
            data = self.client.get(
                f"{FRANKFURTER}/2026-06-01..",
                params={"base": "USD",
                        "symbols": ",".join(DXY_WEIGHTS.keys())},
                timeout=30)
            rates_by_day = data.get("rates", {})
            for day, rates in sorted(rates_by_day.items()):
                try:
                    dxy = self._compute_dxy(rates)
                except (KeyError, ValueError, ZeroDivisionError):
                    continue
                ts = datetime.fromisoformat(day)
                out.append(finalize_observation(
                    "market", "DXY_PROXY", ts, dxy,
                    unit="idx", frequency="daily", category="usd"))
        except Exception as e:  # noqa: BLE001
            logger.warning("[market] dxy proxy failed: %s", e)
        return out

    @staticmethod
    def _compute_dxy(rates: dict) -> float:
        """rates: USD 为 base 时各货币的 USD 价格 (Frankfurter 口径)。
        DXY = C * EURUSD^-w1 * USDJPY^w2 * GBPUSD^-w3 * USDCAD^w4
                  * USDSEK^w5 * USDCHF^-w6  (JPY 使用原始日元报价)
        """
        w = DXY_WEIGHTS
        eurusd = 1.0 / rates["EUR"]
        usdjpy = rates["JPY"]
        gbpusd = 1.0 / rates["GBP"]
        usdcad = rates["CAD"]
        usdsek = rates["SEK"]
        usdchf = 1.0 / rates["CHF"]
        return DXY_CONST * (
            eurusd ** (-w["EUR"]) * usdjpy ** w["JPY"] *
            gbpusd ** (-w["GBP"]) * usdcad ** w["CAD"] *
            usdsek ** w["SEK"] * usdchf ** (-w["CHF"])
        )

    # ---------- 黄金现货 ----------
    def _fetch_gold(self) -> List[Observation]:
        out: List[Observation] = []
        try:
            data = self.client.get(GOLD_API, timeout=20)
            price = data.get("price")
            if price:
                ts = datetime.now().replace(second=0, microsecond=0)
                out.append(finalize_observation(
                    "market", "GOLD_PRICE", ts, float(price),
                    unit="usd", frequency="daily", category="market"))
        except Exception as e:  # noqa: BLE001
            logger.warning("[market] gold failed: %s", e)
        return out

    def fetch(self) -> List[Observation]:
        out: List[Observation] = []
        for fn in (self._fetch_yields, self._fetch_vix,
                   self._fetch_dxy, self._fetch_gold):
            try:
                out += fn()
            except Exception as e:  # noqa: BLE001
                logger.warning("[market] %s failed: %s", fn.__name__, e)
        logger.info("[market] yields=%d vix=%d dxy=%d gold=%d",
                    len([o for o in out if o.series_id.startswith("YC")]),
                    len([o for o in out if o.series_id == "VIX"]),
                    len([o for o in out if o.series_id == "DXY_PROXY"]),
                    len([o for o in out if o.series_id == "GOLD_PRICE"]))
        return out

# ============ 可执行入口 (v1.0) ============
if __name__ == "__main__":
    import logging
    from collections import Counter

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from core.database import Database

    logger.info("[market] starting collection...")
    collector = MarketCollector(env=MarketCollector._env_from_dotenv())
    observations = collector._safe_fetch()

    if not observations:
        logger.warning("[market] no observations fetched")
        _sys.exit(1)

    db = Database("data/macro.db")
    n = db.upsert_many(observations)
    logger.info("[market] saved %d observations", n)

    cnt = Counter(o.series_id for o in observations)
    for sid, c in sorted(cnt.items()):
        logger.info("[market]   %s: %d", sid, c)

    _sys.exit(0)
