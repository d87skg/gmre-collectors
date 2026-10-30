# -*- coding: utf-8 -*-
"""tools/apply_feishu_override.py - 飞书快照（3σ异常熔断 + source精确判断版）"""
import sqlite3
from datetime import datetime
import numpy as np

DB_PATH = 'data/macro.db'

LOCAL_REALTIME_FIELDS = {
    'GOLD_PRICE', 'WTI_OIL', 'YC10Y', 'YC2Y', 'YC30Y', 'VIX',
}

OVERRIDE_MAP = {
    'gold':         ('GOLD_PRICE', 1.0),
    'oil':          ('WTI_OIL', 1.0),
    'dxy':          ('DXY_PROXY', 1.0),
    'usdjpy':       ('USD_JPY', 1.0),
    'vix':          ('VIX', 1.0),
    'us_10y':       ('YC10Y', 1.0),
    'us_2y':        ('YC2Y', 1.0),
    'us_30y':       ('YC30Y', 1.0),
    'hy_oas_bp':    ('HY_SPREAD', 0.01),
    'hy_ccc_bp':    ('HY_CCC_OAS', 0.01),
    'sofr':         ('SOFR', 1.0),
    'effr':         ('EFFR', 1.0),
    'rrp_b':        ('RRP_BALANCE', 1.0),
    'tga_b':        ('TGA_BALANCE', 1000.0),
    'reserve_t':    ('RESERVE_BALANCE', 1000000.0),
}


def check_anomaly(conn, sid, new_val):
    try:
        df = conn.execute(
            "SELECT value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 20",
            (sid,)
        ).fetchall()
        if len(df) < 10:
            return False, None
        vals = [float(r[0]) for r in df]
        mean = np.mean(vals)
        std = np.std(vals)
        if std == 0:
            return False, None
        z_score = abs(new_val - mean) / std
        if z_score > 3.0:
            return True, z_score
        return False, z_score
    except Exception:
        return False, None


def get_local_latest(conn, sid):
    """返回 (date, value, source)"""
    row = conn.execute(
        "SELECT timestamp, value, source FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1",
        (sid,)
    ).fetchone()
    if row:
        date_str = row[0].split(' ')[0].split('T')[0]
        return date_str, float(row[1]), (row[2] or '')
    return None, None, ''


def main():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    try:
        cursor = conn.execute("SELECT * FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            print("❌ feishu_snapshot 表为空")
            return

        cols = [d[0] for d in cursor.description]
        latest = dict(zip(cols, row))
        feishu_date = latest['timestamp'].split(' ')[0]

        print(f"🔄 飞书快照日期: {feishu_date}")

        count = 0
        anomalies = 0
        skipped_realtime = 0
        for field, (series_id, multiplier) in OVERRIDE_MAP.items():
            val = latest.get(field)
            if val is None or val == '':
                continue

            try:
                val = float(val) * multiplier

                local_date, local_val, local_source = get_local_latest(conn, series_id)

                # 1. 本地日期 > 飞书日期则跳过（防旧覆盖）
                if local_date and local_date > feishu_date:
                    print(f"  ⏸️ {series_id:15s} 跳过覆写 (本地 {local_date} > 飞书 {feishu_date})")
                    continue

                # 2. 本地实时源优先：只有"本地实时源"+"今日"+"非昨天飞书写入"才跳过
                #    关键修复：如果 source == 'feishu_override'，说明是昨天飞书写的幽灵数据，允许今天覆写
                today_str = datetime.now().strftime('%Y-%m-%d')
                if series_id in LOCAL_REALTIME_FIELDS and local_date == today_str:
                    if local_source and local_source != 'feishu_override':
                        # 真正的本地实时源（sina/yahoo/stooq/fred_csv等），跳过飞书覆写
                        print(f"  ⏸️ {series_id:15s} 跳过覆写 (本地今日实时源 {local_source}，值 {local_val:.4f})")
                        skipped_realtime += 1
                        continue
                    else:
                        # source 是 feishu_override，说明是昨天飞书写的幽灵数据，允许今日覆写
                        print(f"  🔄 {series_id:15s} 覆盖昨天飞书幽灵值 ({local_val:.4f}) → 今日飞书 {val:.4f}")

                # 3. 3σ 异常熔断
                if series_id in ['GOLD_PRICE', 'WTI_OIL', 'DXY_PROXY', 'USD_JPY', 'VIX', 'YC10Y', 'YC2Y', 'YC30Y']:
                    is_anomaly, z = check_anomaly(conn, series_id, val)
                    if is_anomaly:
                        print(f"  🚨 {series_id:15s} 触发 3σ 熔断! (新值={val:.2f}, Z={z:.2f})，拒绝覆写！")
                        anomalies += 1
                        continue

                # 4. 正常覆写
                conn.execute(
                    """INSERT OR REPLACE INTO observations
                       (series_id, timestamp, value, source, retrieved_at)
                       VALUES (?, ?, ?, 'feishu_override', datetime('now'))""",
                    (series_id, feishu_date, val)
                )
                count += 1
                print(f"  ✅ {series_id:15s} = {val:.4f} (源: 飞书)")
            except Exception as e:
                print(f"  ❌ {field} 写入失败: {e}")

        conn.commit()
        print(f"\n💾 共覆写 {count} 个指标！")
        print(f"   拦截异常 {anomalies} 个 | 本地实时源优先跳过 {skipped_realtime} 个")
    finally:
        conn.close()


if __name__ == '__main__':
    main()