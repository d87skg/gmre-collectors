# -*- coding: utf-8 -*-
"""
补丁 07: data_quality_check.py 的 _load 函数
  - 原: 全局 ORDER BY DESC LIMIT (limit × len(sids))
    → 单一 series (如 VIX 9276 条) 会占满 LIMIT, 挤掉其他 series
  - 新: 每个 series 单独查询 LIMIT N 条, 再 pivot
  - 外部接口不变 (返回 pivot DataFrame)
"""
import shutil
from pathlib import Path

TARGET = Path(r"D:\HGZC\engines_v2\data_quality_check.py")
BACKUP = TARGET.with_suffix(".py.bak_p2b")

shutil.copy2(TARGET, BACKUP)
print("[OK] backup ->", BACKUP)

raw = TARGET.read_text(encoding="utf-8")

old_block = '''def _load(conn, sids, limit=500):
    """加载多个series，返回按日期对齐的DataFrame"""
    placeholders = ','.join(['?'] * len(sids))
    for date_col in ['timestamp', 'date']:
        try:
            df = pd.read_sql_query(
                f"""SELECT {date_col} AS dt, series_id, value FROM observations
                    WHERE series_id IN ({placeholders})
                    ORDER BY {date_col} DESC LIMIT ?""",
                conn, params=sids + [limit * len(sids)]
            )
            if not df.empty:
                df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
                df = df.dropna(subset=['dt'])
                df['dt'] = df['dt'].dt.strftime('%Y-%m-%d')
                df = df.drop_duplicates(subset=['dt', 'series_id'], keep='first')
                pivot = df.pivot_table(index='dt', columns='series_id', values='value')
                return pivot.sort_index()
        except Exception:
            continue
    return pd.DataFrame()
'''

new_block = '''def _load(conn, sids, limit=500):
    """加载多个series，返回按日期对齐的DataFrame

    v2 修复: 每个 series 单独 LIMIT, 避免单一 series 占满全局 LIMIT
    """
    frames = []
    for date_col in ['timestamp', 'date']:
        frames = []
        try:
            for sid in sids:
                df_sid = pd.read_sql_query(
                    f"SELECT {date_col} AS dt, value FROM observations "
                    f"WHERE series_id = ? ORDER BY {date_col} DESC LIMIT ?",
                    conn, params=(sid, limit)
                )
                if not df_sid.empty:
                    df_sid['series_id'] = sid
                    frames.append(df_sid)
        except Exception:
            continue
        if frames:
            break

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
    df = df.dropna(subset=['dt'])
    df['dt'] = df['dt'].dt.strftime('%Y-%m-%d')
    df = df.drop_duplicates(subset=['dt', 'series_id'], keep='first')
    pivot = df.pivot_table(index='dt', columns='series_id', values='value')
    return pivot.sort_index()
'''

if old_block not in raw:
    raise RuntimeError("未找到 _load 原函数, 请核对文件")

raw = raw.replace(old_block, new_block, 1)
print("[OK] replaced _load")

TARGET.write_text(raw, encoding="utf-8")
print("[OK] written ->", TARGET)