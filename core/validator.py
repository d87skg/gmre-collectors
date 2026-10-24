"""数据质量层 (DATA QUALITY): 每次入库前校验, 输出 quality_score 0~1。
维度: NULL / 类型 / 时间戳 / 范围 / 一致性; 后续可升级 SOURCE_RELIABILITY
+ FRESHNESS + COMPLETENESS + CONSISTENCY 合成综合分。
"""
import math
import statistics
from datetime import datetime, timezone
from typing import List, Optional


def validate_value(value) -> float:
    """单值质量分。"""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if not isinstance(value, (int, float)):
        return 0.0
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return 0.0
    return 1.0


def validate_timestamp(ts) -> float:
    if not isinstance(ts, datetime):
        return 0.0
    if ts.year < 1950 or ts.year > 2100:
        return 0.0
    return 1.0


def quality_score_for(ts, value) -> float:
    score = 1.0
    score *= validate_value(value)
    score *= validate_timestamp(ts)
    return max(0.0, min(1.0, score))


def detect_outliers(values: List[float], z_threshold: float = 6.0) -> List[int]:
    """基于 z-score 的简单异常检测, 返回异常索引。"""
    if len(values) < 4:
        return []
    mean = statistics.mean(values)
    stdev = statistics.pstdev(values)
    if stdev == 0:
        return []
    out = []
    for i, v in enumerate(values):
        z = (v - mean) / stdev
        if abs(z) > z_threshold:
            out.append(i)
    return out


def freshness_score(ts: datetime, max_age_days: float = 30.0) -> float:
    """新鲜度: 越旧越低。用于后续 SOURCE 综合分。"""
    age = (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
    if age <= 0:
        return 1.0
    return max(0.0, 1.0 - age / max_age_days)
