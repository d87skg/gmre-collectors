"""统一数据契约 (Unified Observation Schema)。
无论数据来自 FRED / Treasury / ECB / BIS / IMF / WorldBank / SEC /
AlphaVantage / CoinGecko / DeFiLlama / Dune, 最终全部收敛为 Observation。
上层 Factor/Regime 引擎只依赖本契约, 因此新增数据源不需要改动上层。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any


@dataclass
class Observation:
    source: str
    series_id: str
    timestamp: datetime
    value: float
    unit: Optional[str] = None
    frequency: Optional[str] = None
    category: Optional[str] = None
    revision: Optional[float] = None
    quality_score: float = 1.0
    raw_hash: Optional[str] = None


@dataclass
class PolicyEvent:
    """政策事件是一等数据类型（FOMC/BOJ/ECB/PBOC/BOE/Treasury 统一事件）。"""
    event_id: str
    country: str
    institution: str
    event_type: str
    event_time: datetime
    previous_value: Optional[float] = None
    expected_value: Optional[float] = None
    actual_value: Optional[float] = None
    direction: Optional[str] = None          # hawkish | dovish | neutral
    source_url: Optional[str] = None
    evidence_hash: Optional[str] = None


@dataclass
class FactorSnapshot:
    factor_id: str
    timestamp: datetime
    value: float                              # -100 ~ +100
    zscore: float = 0.0
    percentile: float = 50.0
    confidence: float = 1.0                   # 0~1
    components: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)


@dataclass
class RegimeSnapshot:
    timestamp: datetime
    gms: float
    regime: str                               # R0~R5
    confidence: float
    factors: dict
    asset_regimes: dict


@dataclass
class EvidenceRecord:
    evidence_id: str
    source: str
    series: str
    timestamp: str
    raw_value: float
    normalized_value: float
    transformation: str
    factor: str
    layer: str
    hash: str
