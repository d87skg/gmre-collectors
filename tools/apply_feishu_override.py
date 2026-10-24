# -*- coding: utf-8 -*-
"""tools/apply_feishu_override.py - 用飞书快照覆盖本地（3σ异常熔断版）"""
import sqlite3
from datetime import datetime
import numpy as np

DB_PATH = 'data/macro.db'

# 飞书字段 -> (本地 series_id, 换算规则)
OVERRIDE_MAP = {
    # 市场行情
    'gold':         ('GOLD_PRICE', 1.0),
    'oil':          ('WTI_OIL', 1.0),
    'dxy':          ('DXY_PROXY', 1.0),
    'usdjpy':       ('USD_JPY', 1.0),
    'vix':          ('VIX', 1.0),
    
    # 美债收益率
    'us_10y':       ('YC10Y', 1.0),
    'us_2y':        ('YC2Y', 1.0),
    'us_30y':       ('YC30Y', 1.0),
    
    # 信用与流动性
    'hy_oas_bp':    ('HY_SPREAD', 0.01),
    'hy_ccc_bp':    ('HY_CCC_OAS', 0.01),
    'sofr':         ('SOFR', 1.0),
    'effr':         ('EFFR', 1.0),
    'rrp_b':        ('RRP_BALANCE', 1.0),
    'tga_b':        ('TGA_BALANCE', 1000.0),
    'reserve_t':    ('RESERVE_BALANCE', 1000000.0),
}

def check_anomaly(conn, sid, new_val):
    """3σ 异常检测：如果新值偏离近 20 日均值 3 个标准差，视为异常"""
    try:
        # 取过去 20 天的数据（不含今天）
        df = conn.execute(
            "SELECT value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 20", (sid,)
        ).fetchall()
        if len(df) < 10:
            return False, None  # 样本太少，跳过检测
            
        vals = [float(r[0]) for r in df]
        mean = np.mean(vals)
        std = np.std(vals)
        
        if std == 0:
            return False, None
            
        z_score = abs(new_val - mean) / std
        if z_score > 3.0:
            return True, z_score  # 触发异常
        return False, z_score
    except Exception:
        return False, None

def get_local_latest(conn, sid):
    row = conn.execute(
        "SELECT timestamp, value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1", (sid,)
    ).fetchone()
    if row:
        date_str = row[0].split(' ')[0].split('T')[0]
        return date_str, float(row[1])
    return None, None

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
        for field, (series_id, multiplier) in OVERRIDE_MAP.items():
            val = latest.get(field)
            if val is None or val == '':
                continue
                
            try:
                val = float(val) * multiplier
                
                # 1. 日期防旧覆盖
                local_date, local_val = get_local_latest(conn, series_id)
                if local_date and local_date > feishu_date:
                    print(f"  ⏸️ {series_id:15s} 跳过覆写 (本地 {local_date} > 飞书 {feishu_date})")
                    continue
                
                # 2. 3σ 异常熔断（仅针对价格、利率类，避开 RRP/TGA 等极值指标）
                if series_id in ['GOLD_PRICE', 'WTI_OIL', 'DXY_PROXY', 'USD_JPY', 'VIX', 'YC10Y', 'YC2Y', 'YC30Y']:
                    is_anomaly, z = check_anomaly(conn, series_id, val)
                    if is_anomaly:
                        print(f"  🚨 {series_id:15s} 触发 3σ 熔断! (新值={val:.2f}, Z={z:.2f})，拒绝覆写！")
                        anomalies += 1
                        continue

                # 3. 正常覆写
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
        print(f"\n💾 共覆写 {count} 个核心指标！(拦截异常 {anomalies} 个)")
    finally:
        conn.close()

if __name__ == '__main__':
    main()