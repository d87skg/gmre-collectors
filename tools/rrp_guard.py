"""
rrp_guard.py
============================================================
RRP 双源对齐 + 分歧熔断 + 下游门控（最终洁净版）

核心原则：
  1. NYFed 是唯一真理源（实时，T+0）
  2. FRED 只是记录用的参照物（T+1~T+3 延迟）
  3. 只要 NYFed 可用，强制返回 OK，不允许 FRED 干扰主源
  4. 只有 NYFed 过期/缺失，才走降级链路
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
DEFAULT_FRED_SERIES = "RRP_BALANCE"
DEFAULT_NYFED_SERIES = "RRP_NYFED"

DEFAULT_DIVERGENCE_THRESHOLD = 0.05
DEFAULT_RECENT_N = 5
DEFAULT_STALE_DAYS = 4
DEFAULT_LAG_INFO_DAYS = 1


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
    PROCEED = "PROCEED"
    OBSERVE = "OBSERVE"
    BLOCK = "BLOCK"


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
def _load_series_from_db(conn: sqlite3.Connection, series_name: str) -> pd.DataFrame:
    try:
        df = pd.read_sql_query(
            "SELECT timestamp AS ts, value FROM observations "
            "WHERE series_id = ? ORDER BY timestamp",
            conn, params=(series_name,),
        )
    except Exception:
        return pd.DataFrame(columns=["date", "value"])

    if df.empty:
        return pd.DataFrame(columns=["date", "value"])

    df["date"] = pd.to_datetime(df["ts"], errors="coerce").dt.date
    df = df.dropna(subset=["date", "value"])
    df = df.drop_duplicates(subset=["date"], keep="last")
    return df[["date", "value"]].reset_index(drop=True)


# ============================================================
# 对齐 & 检查
# ============================================================
def _align_sources(fred_df: pd.DataFrame, nyfed_df: pd.DataFrame) -> pd.DataFrame:
    if fred_df.empty or nyfed_df.empty:
        return pd.DataFrame(columns=["date", "fred", "nyfed"])
    f = fred_df.rename(columns={"value": "fred"})
    n = nyfed_df.rename(columns={"value": "nyfed"})
    return pd.merge(f, n, on="date", how="inner").sort_values("date").reset_index(drop=True)


def _check_divergence(merged: pd.DataFrame, recent_n: int):
    if merged.empty:
        return None, merged
    recent = merged.tail(recent_n).copy()
    denom = recent["nyfed"].abs().replace(0.0, 1e-9)
    recent["divergence_pct"] = (recent["fred"] - recent["nyfed"]).abs() / denom
    max_div = float(recent["divergence_pct"].max())
    return max_div, recent


def _determine_status(fred_df, nyfed_df, max_div, divergence_threshold,
                      stale_days, lag_info_days, today=None):
    if today is None:
        today = date.today()

    # 1. 双源全无数据
    if fred_df.empty and nyfed_df.empty:
        return RRPStatus.MISSING

    # 2. 核心原则：只要 NYFed 有数据且未过期，直接返回 OK
    if not nyfed_df.empty:
        nyfed_latest_date = nyfed_df["date"].iloc[-1]
        if (today - nyfed_latest_date).days > stale_days:
            return RRPStatus.STALE
        # NYFed 可用，强制直接 OK（忽略 FRED 的任何偏差）
        return RRPStatus.OK

    # 3. NYFed 缺失，降级检查 FRED
    if fred_df.empty:
        return RRPStatus.MISSING

    return RRPStatus.TIME_LAG


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
    if today is None:
        today = date.today()

    fred_df = pd.DataFrame(columns=["date", "value"])
    nyfed_df = pd.DataFrame(columns=["date", "value"])

    if Path(db_path).exists():
        with sqlite3.connect(db_path) as conn:
            fred_df = _load_series_from_db(conn, fred_series)
            nyfed_df = _load_series_from_db(conn, nyfed_series)

    merged = _align_sources(fred_df, nyfed_df)
    max_div, recent_subset = _check_divergence(merged, recent_n)

    fred_value = float(fred_df["value"].iloc[-1]) if not fred_df.empty else None
    fred_date = fred_df["date"].iloc[-1] if not fred_df.empty else None
    nyfed_value = float(nyfed_df["value"].iloc[-1]) if not nyfed_df.empty else None
    nyfed_date = nyfed_df["date"].iloc[-1] if not nyfed_df.empty else None

    # 主源选择：强制优先 NYFed
    if nyfed_value is not None:
        primary_value = nyfed_value
        primary_source = "NYFED"
    elif fred_value is not None:
        primary_value = fred_value
        primary_source = "FRED"
    else:
        primary_value = None
        primary_source = "NONE"

    lag_days = None
    if fred_date is not None and nyfed_date is not None:
        lag_days = (nyfed_date - fred_date).days

    status = _determine_status(
        fred_df=fred_df, nyfed_df=nyfed_df, max_div=max_div,
        divergence_threshold=divergence_threshold,
        stale_days=stale_days, lag_info_days=lag_info_days, today=today,
    )

    if status == RRPStatus.OK:
        action = DownstreamAction.PROCEED
        allow = True
        msg = f"RRP 主源可用 (NYFed={primary_value:.3f}, FRED={fred_value})"
    elif status == RRPStatus.TIME_LAG:
        action = DownstreamAction.PROCEED
        allow = True
        msg = f"RRP 降级 (NYFed 缺失, 使用 FRED={primary_value:.3f})"
    elif status == RRPStatus.STALE:
        action = DownstreamAction.BLOCK
        allow = False
        msg = f"⛔ RRP NYFed 数据过期 ({nyfed_date})，下游阻断"
    else:  # MISSING
        action = DownstreamAction.BLOCK
        allow = False
        msg = "⛔ RRP 双源均无数据，下游阻断"

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


def _fmt(v, unit="$B"):
    return "N/A" if v is None else f"{v:.3f} {unit}"


def _fmt_date(d):
    return d.isoformat() if d else "N/A"


def _log_result(result, recent_subset):
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
            d = row["date"]; f = row["fred"]; n = row["nyfed"]
            div = row.get("divergence_pct", 0.0) * 100.0
            flag = " ⚠️" if div > result.details.get("divergence_threshold_pct", 5.0) else ""
            print(f"    {d}  FRED={f:7.3f}  NYFed={n:7.3f}  Δ={div:6.2f}%{flag}")
    print("=" * 60)


def _parse_args():
    p = argparse.ArgumentParser(description="RRP 双源对齐 + 分歧熔断 + 下游门控")
    p.add_argument("--db", default=DEFAULT_DB_PATH)
    p.add_argument("--fred-series", default=DEFAULT_FRED_SERIES)
    p.add_argument("--nyfed-series", default=DEFAULT_NYFED_SERIES)
    p.add_argument("--threshold", type=float, default=DEFAULT_DIVERGENCE_THRESHOLD)
    p.add_argument("--recent-n", type=int, default=DEFAULT_RECENT_N)
    p.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    p.add_argument("--lag-info-days", type=int, default=DEFAULT_LAG_INFO_DAYS)
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_rrp_guard(
        db_path=args.db, fred_series=args.fred_series, nyfed_series=args.nyfed_series,
        divergence_threshold=args.threshold, recent_n=args.recent_n,
        stale_days=args.stale_days, lag_info_days=args.lag_info_days,
        verbose=not args.quiet and not args.json,
    )
    if args.json:
        import json
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    code_map = {
        RRPStatus.OK: 0, RRPStatus.TIME_LAG: 0,
        RRPStatus.DIVERGENCE: 1, RRPStatus.STALE: 2, RRPStatus.MISSING: 3,
    }
    return code_map.get(result.status, 99)


if __name__ == "__main__":
    sys.exit(main())