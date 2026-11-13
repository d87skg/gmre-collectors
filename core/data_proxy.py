# -*- coding: utf-8 -*-
"""core/data_proxy.py - 只读数据代理层（v4.1 阶段 3 第二步）

所有引擎取数的**唯一入口**。签名与旧 `_load` 对齐：

    load(conn, series_id, limit=60) -> pandas.Series

流水线：别名归一 -> 取数（新表优先）-> 量纲归一 -> 值域净化 -> 截断窗口
        -> 新鲜度校验 -> 血缘日志

四个硬约束：
  1. 日期一律按 **obs_date** 对齐（不是按行数、不是按 timestamp 字符串）；
  2. 量纲一律换算到 units.REGISTRY 的 canonical 单位（TGA=百万美元 / RRP=十亿美元）；
  3. 超区间的脏值（如 RRPONTSYD 的 399600）**绝不返回给引擎**，隔离并抛 DataUnitError；
  4. 陈旧超 SLA 抛 DataStaleError —— 由 core.errors 的三级捕获决定阻断/降级/告警。

缺口一律用 NaN 呈现，本层**不做 ffill/bfill**。
"""
import sqlite3
from datetime import datetime

import pandas as pd

from core import units
from core.errors import (DataUnitError, DataStaleError, DataMissingError,
                         DataQualityError)

# 读表顺序：新表（obs_date 语义完整）优先，迁移态退回 legacy
_OBS_TABLES = (
    ('observations_v2', 'obs_date'),
    ('observations', 'timestamp'),
)


# ---------------------------------------------------------------- 取数
def connect_ro(db_path):
    """只读连接工厂（`mode=ro`）。

    引擎与工具一律通过本函数拿连接，模块内不再出现裸 `sqlite3.connect`——
    这样"读到哪张表、读哪个源"全部收敛在代理层，也不存在误写生产的可能。
    """
    p = str(db_path).replace('\\', '/')
    return sqlite3.connect(f'file:{p}?mode=ro', uri=True)


def _read_one(conn, table, date_col, series_id, limit):
    """从一张表读一个 series，**按 obs_date 分区取每日最新版本**再限量。

    关键：不能先按行 LIMIT 再按日期去重——日内序列（如 BTC_OI_VALUE_HIST 每天
    288 行）会被压成 1 天。这里用窗口函数按自然日分区，保证 limit 的语义是
    「最近 N 个观测日」。
    """
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
    """按 _OBS_TABLES 顺序读，返回第一张有数据的表的结果 + 表名。"""
    for table, date_col in _OBS_TABLES:
        df = _read_one(conn, table, date_col, series_id, limit)
        if df is not None and not df.empty:
            return df, table
    return None, None


def _resolve(conn, series_id, limit):
    """别名链解析，两级策略：

    1) **点名优先**：调用方点名的那个 series_id 只要有数据就原样用它。
       这条最保守——绝不把引擎本来能读到的数据源换成别的序列（否则
       `_load(conn,'HY_SPREAD')` 会被更"新鲜"的兄弟序列劫持，Gate 会漂）。
    2) 该 id 在库里 0 行（如 `HY_OAS` 从未落库）时，才按注册表顺序走别名链，
       取第一个有数据的别名。

    返回 (used_id, df, table, latest_date)。全无数据 raise DataMissingError。
    """
    cid, entry = units.entry_of(series_id)

    df, table = _read_any(conn, series_id, limit)
    if df is not None:
        return series_id, df, table, str(df['dt'].iloc[0])[:10]

    for cand in units.candidates_of(series_id):
        if cand == series_id:
            continue
        df, table = _read_any(conn, cand, limit)
        if df is not None:
            return cand, df, table, str(df['dt'].iloc[0])[:10]

    raise DataMissingError(series_id,
                           context={'candidates': units.candidates_of(series_id)})


# ---------------------------------------------------------------- 清洗
def _clean(df, limit, priority=()):
    """按 obs_date 对齐：取每个观测日最新版本，升序，截断到最近 limit 个观测日。

    `priority` = 注册表里的 `source_priority`（如 `DXY_PROXY` 只认 'market'）。
    有优先级时先按源过滤——同一 series_id 里混装的其它源（fred_csv 的广义美元
    指数）直接不进入引擎，这是"源级物理隔离"的读侧保证。
    """
    df = df.copy()
    df['dt'] = df['dt'].astype(str).str.slice(0, 10)
    df = df[df['dt'].str.len() == 10]
    if priority:
        sel = df[df['source'].isin(priority)]
        if not sel.empty:
            df = sel
    df = df.drop_duplicates(subset=['dt'], keep='first')      # 已按 id DESC，首行即最新版本
    df = df.sort_values('dt').reset_index(drop=True)
    if limit and len(df) > limit:
        df = df.iloc[-int(limit):].reset_index(drop=True)
    return df


def _isolate(conn, series_id, used_id, rows, reason, unit_from, unit_to):
    """把脏行写入 quarantine 隔离区（失败不影响主流程）。"""
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
    """量纲归一 + 值域净化。返回 (clean_df, dirty_df, factor_set, unit_conflicts)。

    单位**以注册表声明为准**：`units.REGISTRY` 里该序列（或该别名）声明的单位
    优先级高于行内 `unit` 列。理由——行内 unit 正是历史上被写坏的那一列
    （迁移前 `unit` 填充率仅 1.2%，污染样本恰恰是 unit 为空的百万级值）。
    行内 unit 只在注册表没有声明时兜底使用；两者冲突时计入 unit_conflicts 供审计。
    """
    cid_e = units.entry_of(series_id)[1]
    canon_unit = cid_e.get('unit')
    declared = units.unit_hint(series_id, used_id)

    out, dirty = [], []
    factors = set()
    conflicts = 0
    nulls = 0
    for _, row in df.iterrows():
        # NULL 是"没采到"，不是"量纲脏"：静默跳过（该日就是缺口），不投隔离区
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


# ---------------------------------------------------------------- 主入口
def load(conn, series_id, limit=60, *, as_index='datetime',
         asof=None, strict_fresh=True, verbose=True, tag=''):
    """代理层唯一取数入口。

    参数
      conn         sqlite3 连接（调用方负责开关）
      series_id    任意叫法（HY_SPREAD / BAMLH0A0HYM2 / US_HY_SPREAD -> HY_OAS）
      limit        取最近多少个**观测日**（按 obs_date 对齐，不是行数）
      as_index     'datetime'（defense_v4 风格）| 'str'（engine_liq 风格）
      asof         新鲜度基准日，默认今天

    返回 pandas.Series（float），缺口为 NaN，绝不 ffill。
    异常：
      DataMissingError  候选全无数据（P2 也照样抛，由上层分级处置）
      DataUnitError     最新观测值是脏值/全部脏值 -> 拒绝喂给引擎
      DataStaleError    days_lag > SLA
    """
    cid, entry = units.entry_of(series_id)
    used_id, df, table, latest = _resolve(conn, series_id, limit)

    df = _clean(df, limit, entry.get('source_priority') or ())
    clean, dirty, factors, unit_conflicts, null_rows = _normalize(df, cid, used_id, conn=conn)

    n_dirty = len(dirty)
    n_clean = len(clean)

    # 全部脏：无可用数据
    if n_clean == 0:
        _isolate(conn, cid, used_id, dirty, 'all_rows_out_of_range',
                 units.unit_hint(cid, used_id), entry.get('unit'))
        raise DataUnitError(
            cid, dirty[0]['value'] if dirty else None,
            *entry.get('range', (None, None)), unit=entry.get('unit'),
            source=used_id, obs_date=dirty[0]['dt'] if dirty else None,
            context={'used_id': used_id, 'dirty_rows': n_dirty, 'clean_rows': 0})

    # 最新观测日是脏值：引擎拿到的"当前值"不可信 -> 抛
    newest = str(df['dt'].iloc[-1])
    if n_dirty and newest in {d['dt'] for d in dirty}:
        _isolate(conn, cid, used_id, dirty, 'newest_row_out_of_range',
                 units.unit_hint(cid, used_id), entry.get('unit'))
        bad = next(d for d in dirty if d['dt'] == newest)
        raise DataUnitError(
            cid, bad['value'], *entry.get('range', (None, None)),
            unit=entry.get('unit'), source=used_id, obs_date=newest,
            context={'used_id': used_id, 'dirty_rows': n_dirty, 'clean_rows': n_clean})

    # 历史脏值：隔离 + 剔除，用干净子集继续
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
    # P2 = 仅展示/告警：数据照常返回，绝不让参考性指标把主流程搞成 N/A。
    # P1 = 降级 UNKNOWN：抛给调用方，由调用方决定"不带这个指标算"。
    # P0 = 阻断：抛给入口，由入口拒绝出报。
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
    """轻量探测：只解析别名与最新观测日，供 preflight 使用（不做量纲/新鲜度判定）。"""
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
    """引擎内部取数的统一封装（阶段 3 第三步：逐个入口接管时都走这里）。

    语义严格对齐 core.errors 的三级分级：
      P0（阻塞型命题，如 TGA）→ 异常向上抛，由入口 `data_preflight` / `guarded_main` 阻断；
      P1（降级型）→ 就地吞掉并返回空 Series，引擎按"该指标不可用"降级，绝不崩；
      P2（展示型）→ 代理层本身就不抛，照常返回。
    """
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
    """load 的容错包装：异常就地按 severity 打印并返回空 Series。

    只给"不能因为一个指标缺失就整段炸掉"的场景用（阶段 3 第三步逐个入口接管时
    视调用点语义选用）；P0 序列仍建议走 load() 让入口阻断。
    """
    from core.errors import format_error
    from core.errors import DataError
    try:
        return load(conn, series_id, limit, **kw)
    except DataError as e:
        print(format_error(e))
        s = pd.Series(dtype=float, name=units.canonical_id(series_id))
        s.attrs['lineage'] = {'error': e.to_dict()}
        return s
