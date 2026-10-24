# -*- coding: utf-8 -*-
"""tools/sync_feishu_snapshot.py - 多分支合并拉取飞书快照（重试+防墙版）"""
import requests
import sqlite3
import csv
import io
import time
from datetime import datetime

DB_PATH = 'data/macro.db'

FIELD_MAP = {
    'gold':             ('GOLD_PRICE',      'direct'),
    'oil':              ('WTI_OIL',         'direct'),
    'dxy':              ('DXY_PROXY',       'direct'),
    'usdjpy':           ('USD_JPY',         'direct'),
    'vix':              ('VIX',             'direct'),
    'us_10y':           ('YC10Y',           'direct'),
    'us_2y':            ('YC2Y',            'direct'),
    'us_30y':           ('YC30Y',           'direct'),
    'hy_oas_bp':        ('HY_SPREAD',       'bp_to_decimal'),
    'hy_ccc_bp':        ('HY_CCC_OAS',      'bp_to_decimal'),
    'sofr':             ('SOFR',            'direct'),
    'effr':             ('EFFR',            'direct'),
    'rrp_b':            ('RRP_BALANCE',     'direct'),
    'tga_b':            ('TGA_BALANCE',     'b_to_m'),
    'reserve_t':        ('RESERVE_BALANCE', 't_to_m'),
}

def fetch_csv():
    """同时拉取主分支和高频分支的快照，合并去重排序"""
    print(f"🔄 正在从 GitHub 拉取多分支 feishu_snapshot.csv ...")
    
    urls = [
        # 老账号 (d87skg) - 低频
        "https://raw.githubusercontent.com/d87skg/gmre-collectors/main/data/feishu_snapshot.csv",
        "https://raw.githubusercontent.com/d87skg/gmre-collectors/data-highfreq/data/feishu_snapshot.csv",
        # 新账号 (jmhbldj) - 高频
        "https://raw.githubusercontent.com/jmhbldj/gmre-collectors/main/data/feishu_snapshot.csv",
        "https://raw.githubusercontent.com/jmhbldj/gmre-collectors/data-highfreq/data/feishu_snapshot.csv"
    ]
    
    all_rows = []
    for url in urls:
        for attempt in range(2):
            try:
                req_url = f"{url}?t={datetime.now().timestamp()}"
                r = requests.get(req_url, timeout=10)
                if r.status_code == 200:
                    reader = csv.DictReader(io.StringIO(r.text))
                    all_rows.extend(list(reader))
                    # 只打印分支名，避免太乱
                    source_name = "main" if "main" in url else "highfreq"
                    engine = "Raw" if "raw" in url else "CDN"
                    print(f"  ✅ 获取成功 ({source_name} @ {engine})")
                    break # 成功则跳出重试循环
            except Exception as e:
                if attempt == 1:
                    print(f"  ⚠️ 拉取失败 ({url[:50]}...): {str(e)[:30]}")
                time.sleep(1)
                
    if not all_rows:
        raise RuntimeError("❌ 所有数据源均不可达，请检查网络。")
        
    # 按 timestamp 去重（字典会保留最后插入的值）
    unique_rows = {}
    for row in all_rows:
        ts = row.get('timestamp')
        if ts:
            unique_rows[ts] = row
            
    # 核心修复：强制按时间排序，确保最后一条是最新的
    sorted_rows = sorted(unique_rows.values(), key=lambda x: x['timestamp'])
    print(f"  🧩 合并去重后，共 {len(sorted_rows)} 条有效快照")
    
    return sorted_rows

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
    elif kind == 'b_to_m':
        return v * 1000.0
    elif kind == 't_to_m':
        return v * 1000000.0
    return v

def save_to_snapshot_table(conn, rows, fieldnames):
    # 核心修复：过滤掉所有为 None 或空字符串的列名，防止拼 SQL 报错
    safe_fields = [c for c in fieldnames if c and isinstance(c, str)]
    cols = ['timestamp'] + [c for c in safe_fields if c != 'timestamp']
    
    col_defs = ', '.join([f"{c} TEXT" for c in cols if c != 'timestamp'])
    conn.execute(f"CREATE TABLE IF NOT EXISTS feishu_snapshot (timestamp TEXT PRIMARY KEY, {col_defs})")

    existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(feishu_snapshot)").fetchall()]
    for c in cols:
        if c not in existing_cols:
            conn.execute(f"ALTER TABLE feishu_snapshot ADD COLUMN {c} TEXT")

    count = 0
    for row in rows:
        placeholders = ', '.join(['?'] * len(cols))
        # 取值时如果遇到 None，自动转为 ''
        values = [row.get(c, '') if row.get(c) is not None else '' for c in cols]
        conn.execute(f"INSERT OR REPLACE INTO feishu_snapshot ({', '.join(cols)}) VALUES ({placeholders})", values)
        count += 1

    # 防膨胀清理
    conn.execute("""
        DELETE FROM feishu_snapshot 
        WHERE rowid NOT IN (
            SELECT rowid FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 20
        )
    """)
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
            continue

        local_date, local_val = row
        local_val_f = float(local_val)

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
    if deviations:
        print(f"  🔴 {len(deviations)} 个显著偏差（>5%）")
    else:
        print(f"  ✅ 所有可比对指标偏差 < 5%，本地数据与飞书一致")
    print(f"{'='*72}\n")

    return deviations

def main():
    try:
        rows = fetch_csv()
        # 由于前面已经按时间排序，最后一条必定是最新数据
        latest = rows[-1]
        print(f"✅ 准备写入 {len(rows)} 条快照，最新时间: {latest.get('timestamp')}")

        conn = sqlite3.connect(DB_PATH, timeout=15)
        try:
            count = save_to_snapshot_table(conn, rows, list(latest.keys()))
            conn.commit()
            print(f"💾 已写入 feishu_snapshot 表: {count} 条（已去重）")
            verify_vs_local(conn, latest)
        finally:
            conn.close()
    except Exception as e:
        print(f"\n❌ 致命错误: {e}")
        print(f"   本次未同步任何数据，本地数据库保持原状。")

if __name__ == "__main__":
    main()