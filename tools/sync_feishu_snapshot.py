# -*- coding: utf-8 -*-
"""tools/sync_feishu_snapshot.py - 飞书快照防覆盖同步"""
import requests
import sqlite3
import csv
import io
import time
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'macro.db')

def fetch_csv():
    print(f"🔄 正在从 GitHub 拉取多分支 feishu_snapshot.csv ...")
    urls = [
        "https://raw.githubusercontent.com/d87skg/gmre-collectors/main/data/feishu_snapshot.csv",
        "https://raw.githubusercontent.com/d87skg/gmre-collectors/data-highfreq/data/feishu_snapshot.csv"
    ]
    all_rows = []
    for url in urls:
        try:
            r = requests.get(f"{url}?t={datetime.now().timestamp()}", timeout=10)
            if r.status_code == 200:
                all_rows.extend(list(csv.DictReader(io.StringIO(r.text))))
                break
        except Exception:
            continue
    unique_rows = {}
    for row in all_rows:
        if row.get('timestamp'):
            unique_rows[row['timestamp']] = row
    return sorted(unique_rows.values(), key=lambda x: x['timestamp'])

def main():
    try:
        rows = fetch_csv()
        if not rows:
            print("❌ 没有拉取到快照数据。")
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(timestamp) FROM feishu_snapshot")
        latest_in_db = cursor.fetchone()[0]

        inserted_count = 0
        # 如果库是空的，或者新数据比库里的新
        if not latest_in_db or rows[-1]['timestamp'] > latest_in_db:
            safe_fields = [c for c in rows[0].keys() if c and isinstance(c, str)]
            col_defs = ', '.join([f"{c} TEXT" for c in safe_fields])
            conn.execute(f"CREATE TABLE IF NOT EXISTS feishu_snapshot ({col_defs}, PRIMARY KEY(timestamp))")

            for row in rows:
                if not latest_in_db or row['timestamp'] > latest_in_db:
                    placeholders = ', '.join(['?'] * len(safe_fields))
                    values = [row.get(c, '') for c in safe_fields]
                    cursor.execute(f"INSERT OR IGNORE INTO feishu_snapshot ({', '.join(safe_fields)}) VALUES ({placeholders})", values)
                    inserted_count += 1
            conn.commit()
            print(f"✅ 成功同步 {inserted_count} 条最新快照数据。")
        else:
            print(f"⏸️ 云端最新快照 ({rows[-1]['timestamp']}) 并不比本地新 ({latest_in_db})，拒绝覆盖。")

        # 缝合逻辑
        if rows:
            latest = rows[-1]
            fr = latest.get('bitget_btc_fr')
            ts_str = latest['timestamp']
            if fr and ts_str:
                try:
                    raw_fr = float(fr) / (3 * 365 * 100)
                    conn.execute("INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at) VALUES ('BTC_FUNDING_RATE_1H', ?, ?, 'feishu_increment', datetime('now'))", (ts_str, raw_fr))
                    conn.commit()
                    print(f"🪡 已缝合最新费率 {fr}% 至历史库。")
                except Exception as e:
                    print(f"⚠️ 费率缝合异常: {e}")
                    
        conn.close()
    except Exception as e:
        print(f"\n❌ 致命错误: {e}")

if __name__ == "__main__":
    main()