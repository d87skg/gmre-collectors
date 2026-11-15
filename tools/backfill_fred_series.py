# tools/backfill_fred_series.py - 修复频率报错与 NOT NULL 约束问题
import sqlite3, os
from datetime import datetime
from fredapi import Fred

DB_PATH = 'data/macro.db'
FRED_API_KEY = os.environ.get('FRED_API_KEY', 'YOUR_KEY_HERE')

SERIES_MAP = {
    'FEDFUNDS': 'FEDFUNDS',
    'MICH_1Y_EXPECT': 'MICH',
    'BROAD_DOLLAR': 'DTWEXBGS',
}

def main():
    if FRED_API_KEY == 'YOUR_KEY_HERE':
        raise SystemExit('请先设置 FRED_API_KEY 环境变量')
    fred = Fred(api_key=FRED_API_KEY)
    conn = sqlite3.connect(DB_PATH)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for gmre_id, fred_id in SERIES_MAP.items():
        row = conn.execute(
            "SELECT MAX(obs_ts) FROM observations WHERE series_id=?", (gmre_id,)
        ).fetchone()
        last_ts = row[0]
        start = None
        if last_ts:
            start = (datetime.fromisoformat(last_ts[:10]).replace(day=1)).strftime('%Y-%m-%d')
        print(f"[{gmre_id}] 库里最新={last_ts or 'EMPTY'}，FRED 拉取起点={start or 'ALL'}")

        try:
            # 完全移除 frequency 参数，避免 API 报错
            series = fred.get_series(fred_id, observation_start=start)
        except Exception as e:
            print(f"  ❌ {gmre_id} 拉取失败: {e}")
            continue

        if series.empty:
            print(f"  ℹ️ {gmre_id} 无新数据")
            continue

        inserted = 0
        for dt, val in series.items():
            if val is None or (isinstance(val, float) and val != val):
                continue
            obs_ts = dt.strftime('%Y-%m-%d')
            obs_date = obs_ts
            
            try:
                # 补充 obs_date 和 ingest_at
                conn.execute(
                    "INSERT OR REPLACE INTO observations "
                    "(series_id, obs_ts, obs_date, ingest_at, value, source) "
                    "VALUES (?, ?, ?, ?, ?, 'fred_api_backfill')",
                    (gmre_id, obs_ts, obs_date, now_str, float(val))
                )
                inserted += 1
            except Exception as ex:
                print(f"  ❌ 插入失败: {ex}")
                break
                    
        conn.commit()
        print(f"  ✅ {gmre_id} 新增 {inserted} 行，最新={series.index[-1].date()}")

    conn.close()

if __name__ == '__main__':
    main()