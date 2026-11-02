"""engines_v2/dau_alert.py - DAU趋势预警（基于IC=-0.05历史验证）"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'
DAU_EXTREME_THRESHOLD = 2.0   # ±2σ触发
DAU_WINDOW = 60                # 60天滚动窗口


def _load_dau():
    """从san_metrics表读取BTC DAU"""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("""
            SELECT datetime, value FROM san_metrics
            WHERE metric='daily_active_addresses' AND slug='bitcoin'
            ORDER BY datetime
        """, conn)
    finally:
        conn.close()

    if df.empty:
        return pd.Series(dtype=float)

    df['dt'] = pd.to_datetime(df['datetime'], format='mixed', utc=True, errors='coerce').dt.date
    df = df.dropna(subset=['dt']).drop_duplicates(subset=['dt'], keep='last')
    return df.set_index('dt')['value'].astype(float).sort_index()


def check_alerts(asof: str) -> dict:
    """检查DAU是否突破±2σ（IC=-0.05，负相关：DAU越高未来收益越低）"""
    dau = _load_dau()

    if len(dau) < DAU_WINDOW:
        return {'asof': asof, 'alert_count': 0, 'alerts': [],
                'error': f'insufficient_data ({len(dau)} days)'}

    # 最近60天滚动均值和标准差
    recent = dau.tail(DAU_WINDOW)
    mean = float(recent.mean())
    std = float(recent.std())
    latest = float(recent.iloc[-1])
    z = (latest - mean) / std if std > 0 else 0.0

    alerts = []

    # DAU过热（+2σ）：按负相关IC，未来60天看跌
    if z > DAU_EXTREME_THRESHOLD:
        alerts.append({
            'level': 'WARNING',
            'type': 'DAU_OVERHEATED',
            'msg': f"⚠️ DAU突破+2σ（Z={z:.2f}）: 链上过热，IC=-0.05历史规律暗示未来60天BTC收益偏弱",
            'metric': {'dau_latest': int(latest), 'dau_mean_60d': int(mean), 'z': round(z, 3)}
        })
    # DAU冷清（-2σ）：按负相关IC，未来60天看涨（机会信号）
    elif z < -DAU_EXTREME_THRESHOLD:
        alerts.append({
            'level': 'INFO',
            'type': 'DAU_OPPORTUNITY',
            'msg': f"ℹ️ DAU跌破-2σ（Z={z:.2f}）: 链上极度冷清，IC=-0.05历史规律暗示未来60天BTC偏强（中长期看多）",
            'metric': {'dau_latest': int(latest), 'dau_mean_60d': int(mean), 'z': round(z, 3)}
        })

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dau_alerts (
            asof_date TEXT, alert_type TEXT, level TEXT, message TEXT, metric TEXT,
            PRIMARY KEY (asof_date, alert_type)
        )
    """)
    for a in alerts:
        conn.execute("""
            INSERT OR REPLACE INTO dau_alerts
            (asof_date, alert_type, level, message, metric)
            VALUES (?, ?, ?, ?, ?)
        """, (asof, a['type'], a['level'], a['msg'], json.dumps(a['metric'])))
    conn.commit()
    conn.close()

    return {
        'asof': asof,
        'alert_count': len(alerts),
        'alerts': alerts,
        'z_score': round(z, 3),
        'latest': int(latest),
        'mean': int(mean)
    }


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = check_alerts(asof)
    print(f"\n{'='*60}")
    print(f"  DAU 趋势预警 - {asof}")
    print(f"{'='*60}")
    print(f"  DAU最新值: {result.get('latest', 'N/A'):,}")
    print(f"  60日均值: {result.get('mean', 'N/A'):,}")
    print(f"  Z-score: {result.get('z_score', 'N/A')}")
    if result['alert_count'] == 0:
        print("  ✅ 无异常")
    else:
        for a in result['alerts']:
            print(f"\n  [{a['level']}] {a['type']}")
            print(f"  {a['msg']}")
    print(f"{'='*60}\n")