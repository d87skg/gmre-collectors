"""Crypto 市场 Collector: CoinGecko 主 / Binance Vision 兜底 (均免费)。
CoinGecko 在某些网络被封时自动切换 Binance 公共行情, 保证 crypto 因子实时。
"""
import logging
from datetime import datetime
from typing import List

from core.normalizer import finalize_observation
from core.schema import Observation

from .base import BaseCollector

logger = logging.getLogger(__name__)

COIN_MAP = {
    "bitcoin": ("BTC_PRICE", "BTC_MCAP", "BTC_24H", "BTC_7D"),
    "ethereum": ("ETH_PRICE", "ETH_MCAP", "ETH_24H", "ETH_7D"),
    "solana": ("SOL_PRICE", None, None, None),
}
# 流通量近似常数 (仅用于兜底估算市值, 标注为 estimate)
SUPPLY = {"bitcoin": 19.9e6, "ethereum": 120.4e6}
BINANCE_SYMBOL = {"bitcoin": "BTCUSDT", "ethereum": "ETHUSDT", "solana": "SOLUSDT"}
BINANCE_BASE = "https://data-api.binance.vision/api/v3"


class CoinGeckoCollector(BaseCollector):
    source_id = "coingecko"
    BASE = "https://api.coingecko.com/api/v3"

    # ---------- CoinGecko 主路径 ----------
    def _fetch_coingecko(self) -> List[Observation]:
        out: List[Observation] = []
        key = self.env.get("COINGECKO_API_KEY")
        headers = {"accept": "application/json"}
        params = {
            "vs_currency": "usd", "order": "market_cap_desc",
            "per_page": "50", "page": "1", "sparkline": "false",
            "price_change_percentage": "24h,7d",
        }
        if key:
            params["x_cg_demo_api_key"] = key
        data = self.client.get(f"{self.BASE}/coins/markets", params=params,
                               headers=headers, timeout=45)
        ts = datetime.now().replace(second=0, microsecond=0)
        for coin in data:
            cid = coin.get("id")
            if cid not in COIN_MAP:
                continue
            price_sid, mcap_sid, chg24_sid, chg7_sid = COIN_MAP[cid]
            if coin.get("current_price") is not None:
                out.append(finalize_observation(
                    "coingecko", price_sid, ts, float(coin["current_price"]),
                    unit="usd", frequency="daily", category="crypto"))
            if mcap_sid and coin.get("market_cap") is not None:
                out.append(finalize_observation(
                    "coingecko", mcap_sid, ts, float(coin["market_cap"]),
                    unit="usd", frequency="daily", category="crypto"))
            if chg24_sid and coin.get("price_change_percentage_24h") is not None:
                out.append(finalize_observation(
                    "coingecko", chg24_sid, ts, float(coin["price_change_percentage_24h"]),
                    unit="%", frequency="daily", category="crypto"))
            if chg7_sid and coin.get("price_change_percentage_7d_in_currency") is not None:
                out.append(finalize_observation(
                    "coingecko", chg7_sid, ts, float(coin["price_change_percentage_7d_in_currency"]),
                    unit="%", frequency="daily", category="crypto"))
        # 全球总市值 + BTC 主导率
        g = self.client.get(f"{self.BASE}/global", headers=headers, timeout=45)
        gd = g.get("data", {})
        if gd.get("total_market_cap", {}).get("usd"):
            out.append(finalize_observation(
                "coingecko", "TOTAL_MCAP", ts,
                float(gd["total_market_cap"]["usd"]),
                unit="usd", frequency="daily", category="crypto"))
        if gd.get("market_cap_percentage", {}).get("btc"):
            out.append(finalize_observation(
                "coingecko", "BTC_DOM", ts,
                float(gd["market_cap_percentage"]["btc"]),
                unit="%", frequency="daily", category="crypto"))
        return out

    # ---------- Binance Vision 兜底 ----------
    def _fetch_binance(self) -> List[Observation]:
        out: List[Observation] = []
        symbols = ",".join(f'"{s}"' for s in BINANCE_SYMBOL.values())
        data = self.client.get(
            f"{BINANCE_BASE}/ticker/24hr",
            params={"symbols": f"[{symbols}]"}, timeout=30)
        ts = datetime.now().replace(second=0, microsecond=0)
        by_sym = {t["symbol"]: t for t in data}
        for cid, (price_sid, mcap_sid, chg24_sid, chg7_sid) in COIN_MAP.items():
            t = by_sym.get(BINANCE_SYMBOL[cid])
            if not t:
                continue
            px = float(t["lastPrice"])
            out.append(finalize_observation(
                "binance", price_sid, ts, px,
                unit="usd", frequency="daily", category="crypto"))
            if chg24_sid:
                out.append(finalize_observation(
                    "binance", chg24_sid, ts, float(t["priceChangePercent"]),
                    unit="%", frequency="daily", category="crypto"))
            if mcap_sid and cid in SUPPLY:
                out.append(finalize_observation(
                    "binance", mcap_sid, ts, px * SUPPLY[cid],
                    unit="usd", frequency="daily", category="crypto"))
            # 7d 变化: klines
            try:
                k = self.client.get(
                    f"{BINANCE_BASE}/klines",
                    params={"symbol": BINANCE_SYMBOL[cid],
                            "interval": "1d", "limit": "10"},
                    timeout=30)
                if chg7_sid and k and len(k) >= 2:
                    prev = float(k[-2][4])  # 8 天前收盘 (klines 旧→新)
                    chg7 = (px - prev) / prev * 100.0
                    out.append(finalize_observation(
                        "binance", chg7_sid, ts, chg7,
                        unit="%", frequency="daily", category="crypto"))
            except Exception as e:  # noqa: BLE001
                logger.warning("[coingecko] binance klines %s failed: %s", cid, e)
        return out

    def fetch(self) -> List[Observation]:
        try:
            return self._fetch_coingecko()
        except Exception as e:  # noqa: BLE001
            logger.warning("[coingecko] primary failed (%s), fallback to binance", e)
            try:
                return self._fetch_binance()
            except Exception as e2:  # noqa: BLE001
                logger.warning("[coingecko] binance fallback failed: %s", e2)
                return []
