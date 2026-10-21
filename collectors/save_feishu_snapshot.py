# -*- coding: utf-8 -*-
"""tools/sync_feishu_snapshot.py - 从 GitHub CSV 拉取飞书快照 + 佐证
"""
import requests
import sqlite3
import csv
import io
from datetime import datetime

DB_PATH = 'data/macro.db'
GITHUB_CSV_URL = "https://raw.githubusercontent.com/d87skg/gmre-collectors/main/data/feishu_snapshot.csv"

# 飞书字段 -> (本地 series_id, 单位换算)
FIELD_MAP = {
    'gold':             ('GOLD_PRICE',      'direct'),
    'oil':              ('WTI_OIL',         'direct'),
    'dxy':              ('DXY_PROXY',       'direct'),
    'usdjpy':           ('USD_JPY',         'direct'),
    'vix':              ('VIX',             'direct'),
    'hy_oas_bp':        ('HY_SPREAD',       'bp_to_decimal'),
    'hy_ccc_bp':        ('HY_CCC_OAS',      'bp_to_decimal'),
    'sofr':             ('SOFR',            'direct'),
    'effr':             ('EFFR',            'direct'),
    'rrp_b':            ('RRP_BALANCE',     'b_to_raw'),
    'tga_b':            ('TGA_BALANCE',     'b_to_raw'),
    'reserve_t':        ('RESERVE_BALANCE', 't_to_raw'),
}


def fetch_csv():
    print(f"🔄 正在从 GitHub 拉取 feishu_snapshot.csv ...")
    r = requests.get(f"{GITHUB_CSV_URL}?t={datetime.now().timestamp()}", timeout=15)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    if not rows:
        raise ValueError("CSV 为空")
    return rows


def convert(val, kind):
    if val is None or val == '':
        return None
    try:
        v = float(val)
    except Exception:
        return None
    if kind == 'direct':
        return v
    elif kind == 'bp_to_decimal':
        return v / 100.0
    elif kind == 'b_to_raw':
        return v * 1e9
    elif kind == 't_to_raw':
        return v * 1e12
    return v


def save_to_snapshot_table(conn, rows, fieldnames):
    cols = ['timestamp'] + [c for c in fieldnames if c != 'timestamp']
    col_defs = ', '.join([f"{c} TEXT" for c in cols])
    conn.execute(f"CREATE TABLE IF NOT EXISTS feishu_snapshot ({col_defs})")

    existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(feishu_snapshot)").fetchall()]
    for c in cols:
        if c not in existing_cols:
            conn.execute(f"ALTER TABLE feishu_snapshot ADD COLUMN {c} TEXT")

    count = 0
    for row in rows:
        placeholders = ', '.join(['?'] * len(cols))
        values = [row.get(c, '') for c in cols]
        conn.execute(f"INSERT INTO feishu_snapshot ({', '.join(cols)}) VALUES ({placeholders})", values)
        count += 1
    return count


def verify_vs_local(conn, latest_row):
    print(f"\n{'='*72}")
    print(f"  🔍 佐证报告：飞书值 vs 本地 observations 最新值")
    print(f"{'='*72}\n")

    deviations = []
    for field, (series_id, kind) in FIELD_MAP.items():
        feishu_val = convert(latest_row.get(field, ''), kind)
        if feishu_val is None:
            continue

        row = conn.execute(
            "SELECT timestamp, value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1",
            (series_id,)
        ).fetchone()
        if not row:
            print(f"  ⚪ {field:20s} 飞书={feishu_val:>14.4f}  本地无 {series_id}")
            continue

        local_date, local_val = row
        local_val_f = float(local_val)

        # 若本地 < 10000 且飞书经换算 > 1e6，反向换算（本地以 B 为单位）
        if kind in ('b_to_raw', 't_to_raw') and local_val_f < 100000:
            feishu_val = feishu_val / 1e9 if kind == 'b_to_raw' else feishu_val / 1e12

        pct_diff = abs(local_val_f - feishu_val) / abs(feishu_val) * 100 if feishu_val != 0 else 0

        if pct_diff < 1:
            flag = "✅"
        elif pct_diff < 5:
            flag = "🟡"
        else:
            flag = "🔴"
            deviations.append((field, feishu_val, local_val_f, pct_diff, local_date))

        print(f"  {flag} {field:20s} 飞书={feishu_val:>14.4f}  本地={local_val_f:>14.4f}  "
              f"偏差={pct_diff:5.2f}%  本地日期={local_date}")

    print(f"\n{'='*72}")
    print(f"  📊 飞书独有字段（本地 observations 无对应，仅存 feishu_snapshot）")
    print(f"{'='*72}\n")
    feishu_only = [k for k in latest_row.keys()
                   if k not in FIELD_MAP and k != 'timestamp' and latest_row[k] not in ('', None)]
    for k in feishu_only[:25]:
        print(f"  ✓  {k:28s} {latest_row[k]}")

    print(f"\n{'='*72}")
    if deviations:
        print(f"  🔴 {len(deviations)} 个显著偏差（>5%），需要排查:")
        for field, fv, lv, diff, ld in deviations:
            print(f"     {field:20s} 飞书={fv:.4f} vs 本地={lv:.4f} (偏差 {diff:.1f}%, 本地 {ld})")
    else:
        print(f"  ✅ 所有可比对指标偏差 < 5%，本地数据与飞书一致")
    print(f"{'='*72}\n")

    return deviations


def main():
    rows = fetch_csv()
    latest = rows[-1]
    print(f"✅ 获取 {len(rows)} 条快照，最新: {latest.get('timestamp')}")

    conn = sqlite3.connect(DB_PATH)
    try:
        count = save_to_snapshot_table(conn, rows, list(latest.keys()))
        conn.commit()
        print(f"💾 已写入 feishu_snapshot 表: {count} 条")
        verify_vs_local(conn, latest)
    finally:
        conn.close()


if __name__ == "__main__":
    main()