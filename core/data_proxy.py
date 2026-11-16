# -*- coding: utf-8 -*-
"""core/data_proxy.py - 只读数据代理层（v4.3: 多源择优版）

关键改动：
  _resolve() 不再返回"第一个有数据的别名"，而是返回"日期最新的那个候选"。
  这是实现多源冗余的核心——主源过期时自动降级到备源。
"""
import sqlite3
from datetime import datetime

import pandas as pd

from core import units
from core.errors import (DataUnitError, DataStaleError, DataMissingError,
                         DataQualityError)

_OBS_TABLES = (
    ('observations_v2', 'obs_date'),
    ('observations', 'timestamp'),
)


def connect_ro(db_path):
    p = str(db_path).replace('\\', '/')
    return sqlite3.connect(f'file:{p}?mode=ro', uri=True)


def _read_one(conn, table, date_col, series_id, limit):
    day = f'substr({date_col}, 1, 10)'
    sql = (f'SELECT dt, value, source, unit FROM ('
           f'  SELECT {day} AS dt, value, source, unit,'
           f'         ROW_NUMBER() OVER (PARTITION BY {day}'
           f'                           ORDER BY {date_col} DESC, id DESC) AS rn'
           f'  FROM {table} WHERE series_id = ?'
           f') WHERE rn = 1 ORDER BY dt DESC LIMIT ?')
    try:
        df = pd.read_sql_query(sql, conn, params=(series_id, int(limit)))
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return None
    if df is None or df.empty:
        return None
    return df


def _read_any(conn, series_id, limit):
    for table, date_col in _OBS_TABLES:
        df = _read_one(conn, table, date_col, series_id, limit)
        if df is not None and not df.empty:
            return df, table
    return None, None


def _resolve(conn, series_id, limit):
    """🆕 在多源候选中选择"日期最新"的那个，实现自动降级。"""
    cid, entry = units.entry_of(series_id)

    # 收集所有候选（去重）
    candidates = [series_id]
    try:
        for cand in units.candidates_of(series_id):
            if cand not in candidates:
                candidates.append(cand)
    except Exception:
        pass

    # 逐个尝试，记录每个候选的最新日期
    results = []
    for cand in candidates:
        df, table = _read_any(conn, cand, limit)
        if df is not None and not df.empty:
            latest = str(df['dt'].iloc[0])[:10]
            results.append((cand, df, table, latest))

    if not results:
        raise DataMissingError(series_id,
                               context={'candidates': candidates})

    # 按日期降序排列，返回最新的那个
    results.sort(key=lambda x: x[3], reverse=True)
    used_id, df, table, latest = results[0]

    # 如果 used_id 不是 canonical 本身，打出降级日志
    if used_id != series_id:
        print(f'  🔀 [proxy] {series_id} 主源缺失/过期，自动降级至备源 {used_id} '
              f'(latest={latest})')

    return used_id, df, table, latest


def _clean(df, limit, priority=(), asof=None):
    df = df.copy()
    df['dt'] = df['dt'].astype(str).str.slice(0, 10)
    df = df[df['dt'].str.len() == 10]
    if asof:
        df = df[df['dt'] <= asof]
    if priority:
        sel = df[df['source'].isin(priority)]
        if not sel.empty:
            df = sel
    df = df.drop_duplicates(subset=['dt'], keep='first')
    df = df.sort_values('dt').reset_index(drop=True)
    if limit and len(df) > limit:
        df = df.iloc[-int(limit):].reset_index(drop=True)
    return df


def _isolate(conn, series_id, used_id, rows, reason, unit_from, unit_to):
    if conn is None or not rows:
        return 0
    moved = 0
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS quarantine (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            series_id TEXT NOT NULL, obs_date TEXT,
                            raw_value REAL, normalized_value REAL,
                            multiplier REAL, unit TEXT,
                            source TEXT NOT NULL DEFAULT 'data_proxy',
                            reason TEXT, payload TEXT, captured_at TEXT NOT NULL,
                            UNIQUE(series_id, obs_date, source))""")
        for r in rows:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO quarantine
                       (series_id, obs_date, raw_value, normalized_value, multiplier,
                        unit, source, reason, payload, captured_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (series_id, r['dt'], r['value'], r['value'], 1.0, unit_from,
                     'data_proxy', reason,
                     f'{{"used_id": "{used_id}", "canonical_unit": "{unit_to}"}}',
                     datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                moved += 1
            except sqlite3.Error:
                pass
        conn.commit()
    except sqlite3.Error:
        return 0
    return moved


def _normalize(df, series_id, used_id, conn=None):
    cid_e = units.entry_of(series_id)[1]
    canon_unit = cid_e.get('unit')
    declared = units.unit_hint(series_id, used_id)

    out, dirty = [], []
    factors = set()
    conflicts = 0
    nulls = 0
    for _, row in df.iterrows():
        if row['value'] is None or pd.isna(row['value']):
            nulls += 1
            continue
        raw_unit = row.get('unit')
        has_row_unit = isinstance(raw_unit, str) and raw_unit.strip() != ''
        if declared:
            fu = declared
            if has_row_unit and raw_unit != declared:
                conflicts += 1
        elif has_row_unit:
            fu = raw_unit
        else:
            fu = canon_unit
        try:
            val, factor, _assumed = units.to_canonical(row['value'], series_id, fu)
        except (TypeError, ValueError):
            dirty.append({'dt': row['dt'], 'value': row['value']})
            continue
        factors.add(factor)
        if not units.in_range(val, series_id):
            dirty.append({'dt': row['dt'], 'value': row['value'],
                          'normalized': val, 'unit_from': fu})
            continue
        out.append({'dt': row['dt'], 'value': val, 'source': row.get('source'),
                    'unit': canon_unit})

    clean = pd.DataFrame(out) if out else pd.DataFrame(columns=['dt', 'value', 'source', 'unit'])
    return clean, dirty, factors, conflicts, nulls


def load(conn, series_id, limit=60, *, as_index='datetime',
         asof=None, strict_fresh=True, verbose=True, tag=''):
    cid, entry = units.entry_of(series_id)
    asof = asof or datetime.now().strftime('%Y-%m-%d')

    used_id, df, table, latest = _resolve(conn, series_id, limit)
    df = _clean(df, limit, entry.get('source_priority') or (), asof=asof)
    clean, dirty, factors, unit_conflicts, null_rows = _normalize(df, cid, used_id, conn=conn)

    n_dirty = len(dirty)
    n_clean = len(clean)

    if n_clean == 0:
        _isolate(conn, cid, used_id, dirty, 'all_rows_out_of_range',
                 units.unit_hint(cid, used_id), entry.get('unit'))
        raise DataUnitError(
            cid, dirty[0]['value'] if dirty else None,
            *entry.get('range', (None, None)), unit=entry.get('unit'),
            source=used_id, obs_date=dirty[0]['dt'] if dirty else None,
            context={'used_id': used_id, 'dirty_rows': n_dirty, 'clean_rows': 0})

    newest = str(df['dt'].iloc[-1])
    if n_dirty and newest in {d['dt'] for d in dirty}:
        _isolate(conn, cid, used_id, dirty, 'newest_row_out_of_range',
                 units.unit_hint(cid, used_id), entry.get('unit'))
        bad = next(d for d in dirty if d['dt'] == newest)
        raise DataUnitError(
            cid, bad['value'], *entry.get('range', (None, None)),
            unit=entry.get('unit'), source=used_id, obs_date=newest,
            context={'used_id': used_id, 'dirty_rows': n_dirty, 'clean_rows': n_clean})

    if n_dirty:
        moved = _isolate(conn, cid, used_id, dirty, 'historical_row_out_of_range',
                         units.unit_hint(cid, used_id), entry.get('unit'))
        if verbose:
            print(f'  🧹 [proxy] {cid} 隔离历史脏值 {n_dirty} 行'
                  f'（quarantine +{moved}），已从返回序列剔除')

    last_date = str(clean['dt'].iloc[-1])
    lag = units.days_lag(last_date, asof)
    sla = entry.get('sla')
    severity = entry.get('severity')

    is_stale = (sla is not None and lag is not None and lag > sla)
    if is_stale and strict_fresh and severity != 'P2':
        raise DataStaleError(cid, lag, sla, obs_date=last_date, source=used_id,
                             context={'used_id': used_id, 'table': table})
    if is_stale and verbose:
        print(f'  ⚠️ [proxy] {cid} 滞后 {lag}d > SLA {sla}d（{severity}）：'
              f'{ "照常返回，仅告警" if severity == "P2" else "已按降级处理" }')

    series = pd.Series(clean['value'].astype(float).values,
                       index=clean['dt'].values, name=cid)
    if as_index == 'datetime':
        series.index = pd.to_datetime(series.index, errors='coerce')
    elif as_index != 'str':
        raise ValueError(f"as_index 只支持 'datetime' / 'str'，收到 {as_index!r}")

    lineage = {
        'requested': series_id, 'canonical': cid, 'used_id': used_id,
        'table': table, 'rows': len(series), 'last_obs_date': last_date,
        'days_lag': lag, 'sla_days': sla, 'severity': entry.get('severity'),
        'stale': bool(is_stale),
        'unit': entry.get('unit'), 'conversion_factors': sorted(factors),
        'isolated_rows': n_dirty, 'unit_conflicts': unit_conflicts,
        'null_rows': null_rows,
    }
    series.attrs['lineage'] = lineage

    if verbose:
        flag = 'OK' if (lag is not None and sla is not None and lag <= sla) else 'STALE'
        alias = '' if used_id == cid else f' (via {used_id})'
        print(f'  🔗 [proxy{(":" + tag) if tag else ""}] {cid}{alias} '
              f'rows={len(series)} last={last_date} lag={lag}d sla={sla}d '
              f'unit={entry.get("unit")} x{sorted(set(factors))} -> {flag}')
    return series


def peek(conn, series_id, asof=None):
    cid, entry = units.entry_of(series_id)
    try:
        used_id, _df, table, latest = _resolve(conn, series_id, 5)
    except (DataMissingError, pd.errors.DatabaseError):
        return None
    return {
        'obs_date': latest, 'series_used': used_id, 'canonical': cid,
        'table': table, 'source': used_id,
        'days_lag': units.days_lag(latest, asof),
        'sla_days': entry.get('sla'),
        'unit': entry.get('unit'),
    }


def load_for_engine(conn, series_id, limit=60, *, as_index='datetime', asof=None):
    from core.errors import DataError, format_error
    try:
        return load(conn, series_id, limit, as_index=as_index, asof=asof, verbose=False)
    except DataError as e:
        if getattr(e, 'severity', 'P2') == 'P0':
            raise
        print('  ⚠️ ' + format_error(e).replace('\n', ' ')[:200])
        s = pd.Series(dtype=float, name=units.canonical_id(series_id))
        s.attrs['lineage'] = {'error': e.to_dict()}
        return s


def load_checked(conn, series_id, limit=60, **kw):
    from core.errors import format_error
    from core.errors import DataError
    try:
        return load(conn, series_id, limit, **kw)
    except DataError as e:
        print(format_error(e))
        s = pd.Series(dtype=float, name=units.canonical_id(series_id))
        s.attrs['lineage'] = {'error': e.to_dict()}
        return s