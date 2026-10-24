"""数据哈希与证据链工具 (Evidence Layer 底座)。"""
import hashlib
import json
from typing import Any


def sha256(payload: Any) -> str:
    if not isinstance(payload, str):
        payload = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def observation_hash(source: str, series_id: str, timestamp, value: float) -> str:
    """原始观测的唯一指纹: source + series + ts + value。"""
    return sha256({
        "source": source,
        "series_id": series_id,
        "timestamp": str(timestamp),
        "value": value,
    })


def factor_hash(factor_id: str, timestamp, value: float, sources: list) -> str:
    return sha256({
        "factor_id": factor_id,
        "timestamp": str(timestamp),
        "value": round(value, 6),
        "sources": sorted(sources),
    })


def chain_hash(hashes: list) -> str:
    """把一条证据链 (observation -> factor -> gms -> regime) 的哈希逐级串联。"""
    acc = "GMDO-CHAIN"
    for h in hashes:
        acc = sha256({"prev": acc, "hash": h})
    return acc
