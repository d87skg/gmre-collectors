"""SQLite 数据库层: 分层表结构 raw -> observation -> factor -> regime -> evidence。"""
import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import FactorSnapshot, Observation, PolicyEvent, RegimeSnapshot
from .pit import estimated_available_at

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    layer TEXT NOT NULL,
    base_url TEXT,
    api_type TEXT,
    requires_key INTEGER DEFAULT 0,
    license_note TEXT,
    enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS series (
    series_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT,
    category TEXT,
    frequency TEXT,
    unit TEXT,
    direction TEXT,
    factor TEXT
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    value REAL,
    revised_value REAL,
    source_timestamp TEXT,
    retrieved_at TEXT NOT NULL,
    quality_score REAL DEFAULT 1.0,
    raw_hash TEXT,
    source TEXT,
    unit TEXT,
    frequency TEXT,
    UNIQUE(series_id, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_obs_series_ts ON observations(series_id, timestamp);

CREATE TABLE IF NOT EXISTS policy_events (
    event_id TEXT PRIMARY KEY,
    country TEXT,
    institution TEXT,
    event_type TEXT,
    event_time TEXT,
    previous_value REAL,
    expected_value REAL,
    actual_value REAL,
    direction TEXT,
    source_url TEXT,
    evidence_hash TEXT
);

CREATE TABLE IF NOT EXISTS factors (
    factor_id TEXT,
    timestamp TEXT,
    value REAL,
    zscore REAL,
    percentile REAL,
    confidence REAL,
    components TEXT,
    sources TEXT,
    PRIMARY KEY(factor_id, timestamp)
);

CREATE TABLE IF NOT EXISTS regimes (
    timestamp TEXT PRIMARY KEY,
    gms REAL,
    regime TEXT,
    raw_regime TEXT,
    confidence REAL,
    factors TEXT,
    asset_regimes TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    source TEXT,
    series TEXT,
    timestamp TEXT,
    raw_value REAL,
    normalized_value REAL,
    transformation TEXT,
    factor TEXT,
    layer TEXT,
    hash TEXT
);
"""


class Database:
    def __init__(self, path: str = "data/macro.db"):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: FastAPI 线程池会跨线程访问连接
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- observations ----------
    def upsert_observation(self, obs: Observation) -> None:
        with self._lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO observations
                (series_id, timestamp, value, revised_value, source_timestamp,
                 retrieved_at, quality_score, raw_hash, source, unit, frequency)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                obs.series_id, obs.timestamp.isoformat(), obs.value, obs.revision,
                None, datetime.now().isoformat(), obs.quality_score, obs.raw_hash,
                obs.source, obs.unit, obs.frequency,
            ))
            self.conn.commit()

    def upsert_many(self, observations: List[Observation]) -> int:
        n = 0
        for obs in observations:
            self.upsert_observation(obs)
            n += 1
        self.conn.commit()
        return n

    def get_series(self, series_id: str, limit: int = 1000,
                   start: Optional[str] = None, end: Optional[str] = None) -> List[sqlite3.Row]:
        sql = "SELECT * FROM observations WHERE series_id=?"
        args: list = [series_id]
        if start:
            sql += " AND timestamp>=?"
            args.append(start)
        if end:
            sql += " AND timestamp<=?"
            args.append(end)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        args.append(limit)
        return list(self.conn.execute(sql, args))

    def get_recent(self, series_id: str, n: int = 5) -> List[sqlite3.Row]:
        return self.get_series(series_id, limit=n)

    def get_latest(self, series_id: str) -> Optional[sqlite3.Row]:
        rows = self.get_series(series_id, limit=1)
        return rows[0] if rows else None

    def latest_value(self, series_id: str) -> Optional[float]:
        row = self.get_latest(series_id)
        return row["value"] if row else None

    def source_stats(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute("""
            SELECT source, COUNT(*) AS obs, MIN(timestamp) AS first_ts,
                   MAX(timestamp) AS last_ts
            FROM observations GROUP BY source ORDER BY obs DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_series_asof(self, series_id: str, asof: datetime, limit: int = 1000):
        """PIT-aware legacy query. Uses explicit publication fields when available;
        otherwise applies the documented legacy availability policy.
        Returns (date,value) ascending.
        """
        rows = self.get_series(series_id, limit=limit)
        out=[]
        for r in rows:
            ts=datetime.fromisoformat(r["timestamp"])
            if r["retrieved_at"] and ts <= asof:
                available = estimated_available_at(series_id, ts)
                if available <= asof:
                    out.append((ts.date(), r["value"]))
        return sorted(out, key=lambda x:x[0])

    # ---------- factors ----------
    def save_factor(self, f: FactorSnapshot) -> None:
        with self._lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO factors
                (factor_id, timestamp, value, zscore, percentile, confidence,
                 components, sources)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                f.factor_id, f.timestamp.isoformat(), f.value, f.zscore,
                f.percentile, f.confidence,
                json.dumps(f.components, default=str), json.dumps(f.sources),
            ))
            self.conn.commit()

    def latest_factors(self) -> Dict[str, float]:
        rows = self.conn.execute("""
            SELECT f.factor_id, f.value, f.confidence
            FROM factors f
            JOIN (SELECT factor_id, MAX(timestamp) AS mt FROM factors
                  GROUP BY factor_id) m
              ON f.factor_id = m.factor_id AND f.timestamp = m.mt
        """).fetchall()
        return {r["factor_id"]: {"value": r["value"], "confidence": r["confidence"]}
                for r in rows}

    # ---------- regimes ----------
    def save_regime(self, r: RegimeSnapshot) -> None:
        with self._lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO regimes
                (timestamp, gms, regime, raw_regime, confidence, factors, asset_regimes)
                VALUES (?,?,?,?,?,?,?)
            """, (
                r.timestamp.isoformat(), r.gms, r.regime,
                getattr(r, "raw_regime", r.regime), r.confidence,
                json.dumps(r.factors, default=str),
                json.dumps(r.asset_regimes, default=str),
            ))
            self.conn.commit()

    def recent_regimes(self, n: int = 5) -> List[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM regimes ORDER BY timestamp DESC LIMIT ?", (n,)))

    def latest_regime(self) -> Optional[sqlite3.Row]:
        rows = self.recent_regimes(1)
        return rows[0] if rows else None

    # ---------- policy events ----------
    def save_policy_event(self, ev: PolicyEvent) -> None:
        with self._lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO policy_events
                (event_id, country, institution, event_type, event_time,
                 previous_value, expected_value, actual_value, direction,
                 source_url, evidence_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ev.event_id, ev.country, ev.institution, ev.event_type,
                ev.event_time.isoformat(), ev.previous_value, ev.expected_value,
                ev.actual_value, ev.direction, ev.source_url, ev.evidence_hash,
            ))
            self.conn.commit()

    def get_policy_events_between(self, start: datetime.date, end: datetime.date):
        rows=self.conn.execute("SELECT * FROM policy_events WHERE event_time BETWEEN ? AND ? ORDER BY event_time ASC",(start.isoformat(),end.isoformat()+"T23:59:59")).fetchall()
        return [dict(r) for r in rows]

    def get_previous_regime(self, eval_date):
        row=self.conn.execute("SELECT * FROM regimes WHERE timestamp < ? ORDER BY timestamp DESC LIMIT 1",(eval_date.isoformat(),)).fetchone()
        return dict(row) if row else None

    # ---------- evidence ----------
    def save_evidence(self, evidence_id: str, source: str, series: str,
                      timestamp: str, raw_value: float, normalized_value: float,
                      transformation: str, factor: str, layer: str,
                      hash_: str) -> None:
        with self._lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO evidence
                (evidence_id, source, series, timestamp, raw_value,
                 normalized_value, transformation, factor, layer, hash)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                evidence_id, source, series, timestamp, raw_value,
                normalized_value, transformation, factor, layer, hash_,
            ))
            self.conn.commit()

    def latest_evidence(self, limit: int = 50) -> List[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM evidence ORDER BY timestamp DESC LIMIT ?", (limit,)))

    def coverage(self) -> Dict[str, Any]:
        n_obs = self.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        n_series = self.conn.execute(
            "SELECT COUNT(DISTINCT series_id) FROM observations").fetchone()[0]
        n_src = self.conn.execute(
            "SELECT COUNT(DISTINCT source) FROM observations").fetchone()[0]
        avg_q = self.conn.execute(
            "SELECT AVG(quality_score) FROM observations").fetchone()[0] or 0.0
        return {"observations": n_obs, "series": n_series, "sources": n_src,
                "avg_quality": round(float(avg_q), 4)}
