# -*- coding: utf-8 -*-
"""tools/sync_feishu_snapshot.py - 飞书快照防覆盖同步（Pandas 自动建表版）"""
import requests
import sqlite3
import csv
import io
import os
import pandas as pd
from datetime import datetime

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
            r = requests.get(f"{url}?t={datetime.now().timestamp()}", timeout=15)
            if r.status_code == 200:
                all_rows.extend(list(csv.DictReader(io.StringIO(r.text))))
                break
        except Exception:
            continue
    return all_rows

def main():
    try:
        rows = fetch_csv()
        if not rows:
            print("❌ 没有拉取到快照数据，跳过写入。")
            return

        # 1. 用 Pandas 处理去重，完全不需要手动拼 SQL
        df_new = pd.DataFrame(rows)
        df_new = df_new.drop_duplicates(subset=['timestamp'], keep='last')
        df_new = df_new.sort_values('timestamp')

        conn = sqlite3.connect(DB_PATH)
        
        # 查库中当前最新时间
        try:
            latest_in_db = pd.read_sql_query("SELECT MAX(timestamp) as max_ts FROM feishu_snapshot", conn).iloc[0]['max_ts']
        except Exception:
            latest_in_db = None

        # 2. 校验：如果库是空的，或者云端最新时间 > 库中时间
        if not latest_in_db or df_new['timestamp'].max() > latest_in_db:
            # 核心修复：不管表存不存在，直接整体 replace，完美解决列名不匹配
            df_new.to_sql('feishu_snapshot', conn, if_exists='replace', index=False)
            print(f"✅ 成功覆写 feishu_snapshot 表 ({len(df_new)} 条)")
            
            # 3. 缝合逻辑：取最新一条费率写入 observations
            latest = df_new.iloc[-1]
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
        else:
            print(f"⏸️ 云端最新快照 ({df_new['timestamp'].max()}) 并不比本地新 ({latest_in_db})，拒绝覆盖。")

        conn.close()
    except Exception as e:
        print(f"\n❌ 致命错误: {e}")

if __name__ == "__main__":
    main()