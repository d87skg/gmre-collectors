"""归一化层: 把原始 payload 转换为统一 Observation; 提供 z-score / percentile。"""
import statistics
from typing import List, Optional

from .schema import Observation
from .validator import quality_score_for


def finalize_observation(source: str, series_id: str, timestamp, value: float,
                         unit: Optional[str] = None,
                         frequency: Optional[str] = None,
                         category: Optional[str] = None) -> Observation:
    from .hashing import observation_hash
    ts = timestamp.replace(tzinfo=None) if timestamp.tzinfo else timestamp
    obs = Observation(
        source=source, series_id=series_id, timestamp=ts, value=float(value),
        unit=unit, frequency=frequency, category=category,
        quality_score=quality_score_for(ts, value),
    )
    obs.raw_hash = observation_hash(source, series_id, ts, float(value))
    return obs


def zscore(value: float, history: List[float]) -> float:
    if len(history) < 3:
        return 0.0
    mean = statistics.mean(history)
    stdev = statistics.pstdev(history)
    if stdev == 0:
        return 0.0
    return (value - mean) / stdev


def percentile_of(value: float, history: List[float]) -> float:
    if not history:
        return 50.0
    below = sum(1 for v in history if v <= value)
    return below / len(history) * 100.0


def pct_change(recent: List[float], window: int = 1) -> Optional[float]:
    """最近值相对 window 天前的变化率 (%), 数据不足返回 None。"""
    if len(recent) < window + 1:
        return None
    prev = recent[window]
    cur = recent[0]
    if prev == 0:
        return None
    return (cur - prev) / prev * 100.0
