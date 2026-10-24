"""
rrp_guard.py
============================================================
RRP 双源对齐 + 分歧熔断 + 下游门控

问题背景 (2026-09-15 日志):
    [WARNING] RRP_SOURCE_DIVERGENCE: 偏差 73.0%
    FRED=5.25, 纽约联储=1.42

根因:
    FRED 最新  = 2026-09-11 (5.255)  ← T+1~T+3 发布延迟
    NYFed 最新 = 2026-09-14 (1.420)  ← 实时
    系统做的是 latest vs latest, 把"3 天时间差"误判为"源分歧"

正确做法:
    1. 必须 merge on date, 同日期比对
    2. 主源 = NYFed (实时), 校验源 = FRED
    3. 分级: OK / TIME_LAG / DIVERGENCE / STALE / MISSING
    4. DIVERGENCE / STALE 时下游降级为 OBSERVE, 不触发 CRITICAL

集成:
    from tools.rrp_guard import run_rrp_guard
    result = run_rrp_guard()
    if result.allow_downstream:
        rrp = result.primary_value
        # 正常驱动 S4 / 防线3
    else:
        # S4 / 防线3 降级为 OBSERVE, 不触发 CRITICAL
============================================================
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

import pandas as pd


# ============================================================
# 配置
# ============================================================
DEFAULT_DB_PATH = r"D:\HGZC\data\macro.db"
DEFAULT_FRED_SERIES = "RRP_BALANCE"     # 来自 FRED RRPONTSYD
DEFAULT_NYFED_SERIES = "RRP_NYFED"      # 来自 NY Fed API

DEFAULT_DIVERGENCE_THRESHOLD = 0.05     # 同日期偏差 > 5% 判定为分歧
DEFAULT_RECENT_N = 5                    # 检查最近 N 个共同日期
DEFAULT_STALE_DAYS = 4                  # NYFed 最新数据超过 N 天判定为 STALE
DEFAULT_LAG_INFO_DAYS = 1               # FRED 滞后超过 N 天仅记录, 不阻断


# ============================================================
# 数据结构
# ============================================================
class RRPStatus(Enum):
    OK = "OK"
    TIME_LAG = "TIME_LAG"
    DIVERGENCE = "DIVERGENCE"
    STALE = "STALE"
    MISSING = "MISSING"


class DownstreamAction(Enum):
    PROCEED = "PROCEED"     # 下游正常执行
    OBSERVE = "OBSERVE"     # 下游降级为观察, 不触发 CRITICAL
    BLOCK = "BLOCK"         # 下游完全阻断


@dataclass
class RRPGuardResult:
    status: RRPStatus
    asof: Optional[date]
    primary_value: Optional[float]
    primary_source: str
    fred_value: Optional[float]
    fred_date: Optional[date]
    nyfed_value: Optional[float]
    nyfed_date: Optional[date]
    same_day_max_divergence_pct: Optional[float]
    lag_days: Optional[int]
    allow_downstream: bool
    downstream_action: DownstreamAction
    message: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "asof": self.asof.isoformat() if self.asof else None,
            "primary_value": self.primary_value,
            "primary_source": self.primary_source,
            "fred_value": self.fred_value,
            "fred_date": self.fred_date.isoformat() if self.fred_date else None,
            "nyfed_value": self.nyfed_value,
            "nyfed_date": self.nyfed_date.isoformat() if self.nyfed_date else None,
            "same_day_max_divergence_pct": self.same_day_max_divergence_pct,
            "lag_days": self.lag_days,
            "allow_downstream": self.allow_downstream,
            "downstream_action": self.downstream_action.value,
            "message": self.message,
            "details": self.details,
        }


# ============================================================
# 数据库加载
# ============================================================
def _load_series_from_db(
    conn: sqlite3.Connection,
    series_name: str,
) -> pd.DataFrame:
    """
    从 observations 表加载 series_id 的时间序列, 返回 DataFrame[date, value]

    observations schema (实际):
        series_id TEXT, timestamp TEXT, value REAL, ...
    处理:
        - timestamp -> date (去时间)
        - dropna(date, value)
        - 同日期多次写入保留最后一条
    """
    try:
        df = pd.read_sql_query(
            "SELECT timestamp AS ts, value FROM observations "
            "WHERE series_id = ? ORDER BY timestamp",
            conn,
            params=(series_name,),
        )
    except Exception:
        return pd.DataFrame(columns=["date", "value"])

    if df.empty:
        return pd.DataFrame(columns=["date", "value"])

    df["date"] = pd.to_datetime(df["ts"], errors="coerce").dt.date
    df = df.dropna(subset=["date", "value"])

    # 同日期多次写入时保留最后一条
    df = df.drop_duplicates(subset=["date"], keep="last")

    return df[["date", "value"]].reset_index(drop=True)


# ============================================================
# 对齐 & 检查
# ============================================================
def _align_sources(fred_df: pd.DataFrame, nyfed_df: pd.DataFrame) -> pd.DataFrame:
    """
    只做同日期对齐 (merge on date), 不做 latest vs latest
    """
    if fred_df.empty or nyfed_df.empty:
        return pd.DataFrame(columns=["date", "fred", "nyfed"])

    f = fred_df.rename(columns={"value": "fred"})
    n = nyfed_df.rename(columns={"value": "nyfed"})
    merged = pd.merge(f, n, on="date", how="inner").sort_values("date").reset_index(drop=True)
    return merged


def _check_divergence(
    merged: pd.DataFrame,
    recent_n: int,
    threshold: float,
) -> tuple[Optional[float], pd.DataFrame]:
    """
    返回 (最近 N 个共同日期的最大偏差, 被检查的子集)
    """
    if merged.empty:
        return None, merged

    recent = merged.tail(recent_n).copy()
    denom = recent["nyfed"].abs().replace(0.0, 1e-9)
    recent["divergence_pct"] = (recent["fred"] - recent["nyfed"]).abs() / denom

    max_div = float(recent["divergence_pct"].max())
    return max_div, recent


def _determine_status(
    fred_df: pd.DataFrame,
    nyfed_df: pd.DataFrame,
    max_div: Optional[float],
    divergence_threshold: float,
    stale_days: int,
    lag_info_days: int,
    today: Optional[date] = None,
) -> RRPStatus:
    if today is None:
        today = date.today()

    # 1. 数据缺失
    if fred_df.empty and nyfed_df.empty:
        return RRPStatus.MISSING

    # 2. NYFed 数据过期
    if not nyfed_df.empty:
        nyfed_latest_date = nyfed_df["date"].iloc[-1]
        if (today - nyfed_latest_date).days > stale_days:
            return RRPStatus.STALE

    # 3. 同日期分歧
    if max_div is not None and max_div > divergence_threshold:
        return RRPStatus.DIVERGENCE

    # 4. 记录性 TIME_LAG (不阻断)
    if not fred_df.empty and not nyfed_df.empty:
        lag = (nyfed_df["date"].iloc[-1] - fred_df["date"].iloc[-1]).days
        if lag > lag_info_days:
            return RRPStatus.TIME_LAG

    return RRPStatus.OK


# ============================================================
# 主入口
# ============================================================
def run_rrp_guard(
    db_path: str = DEFAULT_DB_PATH,
    fred_series: str = DEFAULT_FRED_SERIES,
    nyfed_series: str = DEFAULT_NYFED_SERIES,
    divergence_threshold: float = DEFAULT_DIVERGENCE_THRESHOLD,
    recent_n: int = DEFAULT_RECENT_N,
    stale_days: int = DEFAULT_STALE_DAYS,
    lag_info_days: int = DEFAULT_LAG_INFO_DAYS,
    today: Optional[date] = None,
    verbose: bool = True,
) -> RRPGuardResult:
    """
    RRP 双源对齐 + 分歧熔断 + 下游门控

    返回 RRPGuardResult, 供 data_correction / S4 / 防线3 统一消费
    """
    if today is None:
        today = date.today()

    # --- 加载 ---
    fred_df = pd.DataFrame(columns=["date", "value"])
    nyfed_df = pd.DataFrame(columns=["date", "value"])

    db_exists = Path(db_path).exists()
    if db_exists:
        with sqlite3.connect(db_path) as conn:
            fred_df = _load_series_from_db(conn, fred_series)
            nyfed_df = _load_series_from_db(conn, nyfed_series)

    # --- 对齐 ---
    merged = _align_sources(fred_df, nyfed_df)
    max_div, recent_subset = _check_divergence(merged, recent_n, divergence_threshold)

    # --- 提取最新值 ---
    fred_value = float(fred_df["value"].iloc[-1]) if not fred_df.empty else None
    fred_date = fred_df["date"].iloc[-1] if not fred_df.empty else None
    nyfed_value = float(nyfed_df["value"].iloc[-1]) if not nyfed_df.empty else None
    nyfed_date = nyfed_df["date"].iloc[-1] if not nyfed_df.empty else None

    # --- 主源选择 ---
    if nyfed_value is not None:
        primary_value = nyfed_value
        primary_source = "NYFED"
    elif fred_value is not None:
        primary_value = fred_value
        primary_source = "FRED"
    else:
        primary_value = None
        primary_source = "NONE"

    # --- 滞后天数 ---
    lag_days: Optional[int] = None
    if fred_date is not None and nyfed_date is not None:
        lag_days = (nyfed_date - fred_date).days

    # --- 状态判定 ---
    status = _determine_status(
        fred_df=fred_df,
        nyfed_df=nyfed_df,
        max_div=max_div,
        divergence_threshold=divergence_threshold,
        stale_days=stale_days,
        lag_info_days=lag_info_days,
        today=today,
    )

    # --- 下游动作 ---
    if status == RRPStatus.OK:
        action = DownstreamAction.PROCEED
        allow = True
        msg = f"RRP 双源一致 (primary={primary_source}={primary_value:.3f})"
    elif status == RRPStatus.TIME_LAG:
        action = DownstreamAction.PROCEED
        allow = True
        msg = (
            f"RRP 存在发布延迟 (FRED 滞后 {lag_days} 天), "
            f"使用 NYFed 实时值 {nyfed_value:.3f}, 下游正常"
        )
    elif status == RRPStatus.DIVERGENCE:
        action = DownstreamAction.OBSERVE
        allow = False
        msg = (
            f"⚠️ RRP 同日期分歧 {max_div * 100:.1f}% > {divergence_threshold * 100:.1f}%, "
            f"下游降级为 OBSERVE, 不触发 CRITICAL"
        )
    elif status == RRPStatus.STALE:
        action = DownstreamAction.BLOCK
        allow = False
        msg = f"⛔ RRP 数据过期 (NYFed 最新 {nyfed_date}), 下游阻断"
    else:  # MISSING
        action = DownstreamAction.BLOCK
        allow = False
        msg = "⛔ RRP 双源均无数据, 下游阻断"

    result = RRPGuardResult(
        status=status,
        asof=nyfed_date or fred_date,
        primary_value=primary_value,
        primary_source=primary_source,
        fred_value=fred_value,
        fred_date=fred_date,
        nyfed_value=nyfed_value,
        nyfed_date=nyfed_date,
        same_day_max_divergence_pct=(max_div * 100.0) if max_div is not None else None,
        lag_days=lag_days,
        allow_downstream=allow,
        downstream_action=action,
        message=msg,
        details={
            "aligned_common_days": int(len(merged)),
            "recent_check_days": int(len(recent_subset)),
            "divergence_threshold_pct": divergence_threshold * 100.0,
            "stale_days": stale_days,
        },
    )

    if verbose:
        _log_result(result, recent_subset)

    return result


# ============================================================
# 日志输出
# ============================================================
def _fmt(v: Optional[float], unit: str = "$B") -> str:
    if v is None:
        return "N/A"
    return f"{v:.3f} {unit}"


def _fmt_date(d: Optional[date]) -> str:
    return d.isoformat() if d else "N/A"


def _log_result(result: RRPGuardResult, recent_subset: pd.DataFrame) -> None:
    print("=" * 60)
    print("  RRP Guard - 双源对齐检查")
    print("=" * 60)
    print(f"  Status       : {result.status.value}")
    print(f"  As of        : {_fmt_date(result.asof)}")
    print(f"  FRED         : {_fmt(result.fred_value)} @ {_fmt_date(result.fred_date)}")
    print(f"  NYFed        : {_fmt(result.nyfed_value)} @ {_fmt_date(result.nyfed_date)}")
    print(f"  Primary      : {result.primary_source} = {_fmt(result.primary_value)}")
    if result.lag_days is not None:
        print(f"  Lag (FRED→NY): {result.lag_days} 天")
    if result.same_day_max_divergence_pct is not None:
        print(f"  同日期偏差    : {result.same_day_max_divergence_pct:.2f}%")
    print(f"  Downstream   : {result.downstream_action.value} (allow={result.allow_downstream})")
    print(f"  Message      : {result.message}")

    if not recent_subset.empty:
        print("-" * 60)
        print("  最近 N 个共同日期:")
        for _, row in recent_subset.iterrows():
            d = row["date"]
            f = row["fred"]
            n = row["nyfed"]
            div = row.get("divergence_pct", 0.0) * 100.0
            flag = " ⚠️" if div > result.details.get("divergence_threshold_pct", 5.0) else ""
            print(f"    {d}  FRED={f:7.3f}  NYFed={n:7.3f}  Δ={div:6.2f}%{flag}")

    print("=" * 60)


# ============================================================
# CLI
# ============================================================
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RRP 双源对齐 + 分歧熔断 + 下游门控")
    p.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite 路径")
    p.add_argument("--fred-series", default=DEFAULT_FRED_SERIES, help="FRED 序列名")
    p.add_argument("--nyfed-series", default=DEFAULT_NYFED_SERIES, help="NYFed 序列名")
    p.add_argument("--threshold", type=float, default=DEFAULT_DIVERGENCE_THRESHOLD,
                   help="同日期偏差阈值 (默认 0.05 = 5%%)")
    p.add_argument("--recent-n", type=int, default=DEFAULT_RECENT_N,
                   help="检查最近 N 个共同日期 (默认 5)")
    p.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS,
                   help="NYFed 数据过期阈值 (默认 4 天)")
    p.add_argument("--lag-info-days", type=int, default=DEFAULT_LAG_INFO_DAYS,
                   help="FRED 滞后记录阈值 (默认 1 天)")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    p.add_argument("--quiet", action="store_true", help="不打印详细日志")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    result = run_rrp_guard(
        db_path=args.db,
        fred_series=args.fred_series,
        nyfed_series=args.nyfed_series,
        divergence_threshold=args.threshold,
        recent_n=args.recent_n,
        stale_days=args.stale_days,
        lag_info_days=args.lag_info_days,
        verbose=not args.quiet and not args.json,
    )

    if args.json:
        import json
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    # 退出码: OK/TIME_LAG=0, DIVERGENCE=1, STALE=2, MISSING=3
    code_map = {
        RRPStatus.OK: 0,
        RRPStatus.TIME_LAG: 0,
        RRPStatus.DIVERGENCE: 1,
        RRPStatus.STALE: 2,
        RRPStatus.MISSING: 3,
    }
    return code_map.get(result.status, 99)


if __name__ == "__main__":
    sys.exit(main())