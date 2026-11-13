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


# =============================================================================
# v4.1 观测值写入辅助（append-only + 血缘）
# =============================================================================
def _coerce_obs_ts(v) -> str:
    """把时间戳统一成可比较的全精度字符串。

    保留原有粒度：日频序列保持 'YYYY-MM-DD'，日内序列保持 'YYYY-MM-DD HH:MM:SS'
    ——**不得截断日内精度**，否则 BTC_OI 这类 288 点/天的序列会被压扁。
    """
    if isinstance(v, datetime):
        return v.isoformat(sep=' ', timespec='seconds')
    if hasattr(v, 'isoformat') and not isinstance(v, str):
        return v.isoformat()[:19]
    return str(v).strip()[:19]


def _coerce_obs_date(v) -> str:
    """从全精度时间戳派生日期部分 'YYYY-MM-DD'。"""
    return _coerce_obs_ts(v)[:10]


def _coerce_ingest(v) -> str:
    """入库时刻统一成 'YYYY-MM-DD HH:MM:SS.mmm'（毫秒精度，用于唯一键排序）。"""
    dt = v if isinstance(v, datetime) else datetime.now()
    return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def _bump_ms(ingest_str: str, ms: int = 1) -> str:
    """唯一键撞车时把 ingest_at 顺延 ms 毫秒。"""
    try:
        dt = datetime.strptime(ingest_str, '%Y-%m-%d %H:%M:%S.%f')
    except ValueError:
        dt = datetime.now()
    from datetime import timedelta
    return (dt + timedelta(milliseconds=ms)).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def _same_value(a, b) -> bool:
    """同值判定：两次轮询拿到同一个数时不应产生新行。"""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(fa - fb) <= max(1e-12, 1e-9 * max(abs(fa), abs(fb)))


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
    obs_ts TEXT NOT NULL,
    obs_date TEXT NOT NULL,
    timestamp TEXT GENERATED ALWAYS AS (obs_ts) VIRTUAL,
    ingest_at TEXT,
    value REAL,
    revised_value REAL,
    source_timestamp TEXT,
    retrieved_at TEXT,
    quality_score REAL DEFAULT 1.0,
    raw_hash TEXT,
    source TEXT NOT NULL DEFAULT 'unknown',
    unit TEXT,
    frequency TEXT,
    revision_of INTEGER,
    import_batch TEXT,
    obs_date_confidence TEXT NOT NULL DEFAULT 'derived',
    rev_seq INTEGER NOT NULL DEFAULT 0,        -- 同一 (series, obs_ts, source) 的版本序号 0,1,2...
    UNIQUE(series_id, obs_ts, source, rev_seq)
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

    # ---------- observations (v4.1: append-only + 血缘) ----------
    def _resolve_obs_table(self) -> Optional[str]:
        """返回当前可用的观测表名。

        优先 'observations'（cutover 后即为 v2 表），否则退回 'observations_v2'
        （--apply 迁移完成但尚未 cutover 的过渡态）。
        两者都缺 obs_ts/obs_date 时返回 None，调用方必须拒绝写入。
        """
        for t in ('observations', 'observations_v2'):
            cols = [r[1] for r in self.conn.execute(f"PRAGMA table_info('{t}')")]
            if cols and 'obs_ts' in cols and 'obs_date' in cols:
                return t
        return None

    def insert_observation(self, series_id: str, obs_ts, value: Optional[float], *,
                           obs_date: Optional[str] = None,
                           source: Optional[str] = None,
                           unit: Optional[str] = None,
                           frequency: Optional[str] = None,
                           ingest_at: Optional[datetime] = None,
                           revised_value: Optional[float] = None,
                           source_timestamp: Optional[str] = None,
                           raw_hash: Optional[str] = None,
                           quality_score: float = 1.0,
                           obs_date_confidence: str = 'derived',
                           import_batch: Optional[str] = None) -> tuple[int, bool]:
        """追加式写入一条观测值。返回 (row_id, created)。

        自然键 = (series_id, obs_ts, source)，obs_ts 保留**全精度**时间戳。
        这点很关键：BTC_OI_VALUE_HIST 这类日内序列同一天有 288 个点，
        若用 obs_date 做键，日内精度会被压扁成一天一条。

        覆写冲突的三种处理（无 REPLACE，无覆盖）：
        ① 同值幂等：同键已存在且值未变 -> 不新增行，返回旧 id（created=False）。
           历史库里有约 34.9 万行属于这种重复轮询痕迹，幂等能从源头止住增长。
        ② 异值修订：值变化 -> 追加新行，revision_of 链到上一条 id，旧行原样保留。
           时间序由 ingest_at 表达，"最新版本" = ingest_at / id 最大的那条。
        ③ 并发撞键：键已含 obs_ts，正常不会撞；万一并发插入同一键，
           回读上一条并作为修订行重试，依然追加而非覆盖。
        """
        table = self._resolve_obs_table()
        if table is None:
            raise RuntimeError(
                'observations 表尚未迁移（缺 obs_ts/obs_date），'
                '请先运行 migrations/001_observations_v2.py --apply')

        ts = _coerce_obs_ts(obs_ts)
        od = obs_date or ts[:10]
        src = source or 'unknown'
        ing = _coerce_ingest(ingest_at)

        with self._lock:
            prev = self._fetch_prev(table, series_id, ts, src)

            # ① 同值幂等
            if prev is not None and _same_value(prev['value'], value):
                return int(prev['id']), False

            for _ in range(2):
                # ② 异值修订
                rev_seq = int(prev['rev_seq']) + 1 if prev is not None else 0
                revision_of = int(prev['id']) if prev is not None else None
                try:
                    cur = self.conn.execute(
                        f"""INSERT INTO {table}
                            (series_id, obs_ts, obs_date, ingest_at, value, revised_value,
                             source_timestamp, retrieved_at, quality_score, raw_hash,
                             source, unit, frequency, revision_of, import_batch,
                             obs_date_confidence, rev_seq)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (series_id, ts, od, ing, value, revised_value,
                         source_timestamp, ing, quality_score, raw_hash,
                         src, unit, frequency, revision_of, import_batch,
                         obs_date_confidence, rev_seq))
                    self.conn.commit()
                    return int(cur.lastrowid), True
                except sqlite3.IntegrityError:
                    # ③ 并发撞键：回读上一条，作为修订行重试
                    prev = self._fetch_prev(table, series_id, ts, src)
                    if prev is None:
                        raise

            raise RuntimeError(
                f'insert_observation 键冲突无法消解: {series_id} @ {ts} / {src}')

    def _fetch_prev(self, table: str, series_id: str, ts: str, src: str):
        """取同键最新版本，用于同值判定、revision_of 链接与 rev_seq 递增。"""
        return self.conn.execute(
            f"""SELECT id, value, rev_seq FROM {table}
                WHERE series_id = ? AND obs_ts = ? AND source = ?
                ORDER BY rev_seq DESC, id DESC LIMIT 1""",
            (series_id, ts, src)).fetchone()

    def upsert_observation(self, obs: Observation) -> None:
        """向后兼容包装。

        语义已从 INSERT OR REPLACE 变为 append-only：同名同日的更新会生成
        带 revision_of 的修订行，而不是覆盖历史。
        """
        self.insert_observation(
            obs.series_id, obs.timestamp, obs.value,
            source=obs.source, unit=obs.unit, frequency=obs.frequency,
            revised_value=getattr(obs, 'revision', None),
            raw_hash=obs.raw_hash, quality_score=obs.quality_score,
        )

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
