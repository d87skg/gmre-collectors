"""engines_v2/liquidity_alert.py - 流动性拐点预警（最终校准版）"""
import sqlite3
import pandas as pd
import json
from datetime import datetime

DB_PATH = 'data/macro.db'

# ============ 阈值（单位：十亿美元） ============
RRP_DEPLETION_THRESHOLD = 20.0      # RRP低于200亿美元视为接近耗尽
RRP_DRAIN_WARNING = 200.0           # RRP 20日流出超过2000亿视为加速
NET_LIQ_SPIKE_THRESHOLD = 3000.0    # 净流动性20日变化超过3万亿视为异动（匹配周频数据）
INF_BREAKDOWN_THRESHOLD = -1.5
MON_PASSIVE_TIGHTEN = 1.0


def _load_series(conn, sid, lookback=300):
    for date_col in ['timestamp', 'date']:
        try:
            df = pd.read_sql_query(
                f"SELECT {date_col} AS dt, value FROM observations "
                f"WHERE series_id=? ORDER BY {date_col} DESC LIMIT ?",
                conn, params=(sid, lookback)
            )
            if not df.empty:
                df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
                df = df.dropna(subset=['dt']).drop_duplicates(subset=['dt'], keep='first')
                return df.sort_values('dt').set_index('dt')['value'].rename(sid)
        except Exception:
            continue
    return pd.Series(dtype=float, name=sid)


def check_alerts(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        walcl = _load_series(conn, 'FED_WALCL', 300)
        tga = _load_series(conn, 'TGA_BALANCE', 300)
        rrp = _load_series(conn, 'RRP_BALANCE', 300)

        latests = pd.read_sql_query(
            "SELECT engine_id, z_score FROM engine_latents WHERE asof_date=?",
            conn, params=(asof,)
        )
        z_scores = dict(zip(latests['engine_id'], latests['z_score']))
    finally:
        conn.close()

    df = pd.concat([walcl, tga, rrp], axis=1).sort_index()
    df = df.ffill().bfill()
    if df.empty or len(df) < 21:
        return {'asof': asof, 'alert_count': 0, 'alerts': [], 'error': 'insufficient_data'}

    # 三个序列全是"百万美元"，统一 ÷1000 变成"十亿美元"
    df['WALCL_B'] = df['FED_WALCL'] / 1000.0
    df['TGA_B'] = df['TGA_BALANCE'] / 1000.0
    df['RRP_B'] = df['RRP_BALANCE']   # RRP已是十亿美元
    df['NET_LIQ'] = df['WALCL_B'] - df['TGA_B'] - df['RRP_B']

    alerts = []

    # ============ 预警1：RRP 耗尽 ============
    rrp_now = float(df['RRP_B'].iloc[-1])
    rrp_20 = float(df['RRP_B'].iloc[-min(20, len(df))])
    rrp_20d_chg = rrp_now - rrp_20

    if rrp_now < RRP_DEPLETION_THRESHOLD:
        alerts.append({
            'level': 'CRITICAL',
            'type': 'RRP_DEPLETION',
            'msg': f"⚠️ RRP 余额仅 {rrp_now*10:.1f} 亿美元（{rrp_now:.2f} 十亿），接近耗尽",
            'metric': {'rrp_billion_usd': round(rrp_now, 3)}
        })
    elif rrp_20d_chg < -RRP_DRAIN_WARNING:
        alerts.append({
            'level': 'WARNING',
            'type': 'RRP_ACCELERATED_DRAIN',
            'msg': f"⚠️ RRP 20日加速流出 {abs(rrp_20d_chg)*10:.1f} 亿美元",
            'metric': {'rrp_20d_chg_billion': round(rrp_20d_chg, 3)}
        })

    # ============ 预警1.5：RRP 双源交叉验证 ============
    try:
        conn = sqlite3.connect(DB_PATH)
        rrp_fred = _load_series(conn, 'RRP_BALANCE', 5)
        rrp_nyfed = _load_series(conn, 'RRP_NYFED', 5)
        conn.close()

        if len(rrp_fred) >= 1 and len(rrp_nyfed) >= 1:
            fred_val = float(rrp_fred.iloc[-1])       # 十亿美元
            nyfed_val = float(rrp_nyfed.iloc[-1])     # 十亿美元

            # 两者理论上应该一致（差异<5%为正常）
            if fred_val > 0:
                divergence_pct = abs(fred_val - nyfed_val) / fred_val * 100
                if divergence_pct > 15:
                    alerts.append({
                        'level': 'WARNING',
                        'type': 'RRP_SOURCE_DIVERGENCE',
                        'msg': f"⚠️ RRP数据源偏差 {divergence_pct:.1f}%：FRED={fred_val:.2f}, 纽约联储={nyfed_val:.2f}，建议人工复核",
                        'metric': {
                            'fred_billion': round(fred_val, 3),
                            'nyfed_billion': round(nyfed_val, 3),
                            'divergence_pct': round(divergence_pct, 2)
                        }
                    })
    except Exception:
        pass

    # ============ 预警2：净流动性异动（20日窗口） ============
    net_now = float(df['NET_LIQ'].iloc[-1])
    net_20d = float(df['NET_LIQ'].iloc[-min(20, len(df))])
    net_chg = net_now - net_20d

    if abs(net_chg) > NET_LIQ_SPIKE_THRESHOLD:
        direction = '注入' if net_chg > 0 else '抽离'
        alerts.append({
            'level': 'WARNING',
            'type': 'NET_LIQ_SPIKE',
            'msg': f"⚠️ 净流动性20日{direction} {abs(net_chg)*10:.1f} 亿美元",
            'metric': {'net_liq_now_b': round(net_now, 2), 'net_liq_20d_chg_b': round(net_chg, 3)}
        })

    # ============ 预警3：通胀加速下行 ============
    inf_z = z_scores.get('INF', 0.0)
    if inf_z < INF_BREAKDOWN_THRESHOLD:
        alerts.append({
            'level': 'WARNING',
            'type': 'INFLATION_BREAKDOWN',
            'msg': f"⚠️ INF Z-score={inf_z:.2f} 已破 -1.5",
            'metric': {'INF': round(inf_z, 3)}
        })

    # ============ 预警4：被动紧缩共振 ============
    mon_z = z_scores.get('MON', 0.0)
    if mon_z > MON_PASSIVE_TIGHTEN and inf_z < -1.0:
        alerts.append({
            'level': 'CRITICAL',
            'type': 'PASSIVE_TIGHTENING',
            'msg': f"🚨 被动紧缩共振：INF={inf_z:.2f} + MON={mon_z:.2f}",
            'metric': {'INF': round(inf_z, 3), 'MON': round(mon_z, 3)}
        })

    # ============ 预警5：R4/R5 体制切换压力 ============
    try:
        conn = sqlite3.connect(DB_PATH)
        regime_row = pd.read_sql_query(
            "SELECT regime_probs FROM gms_regimes WHERE asof_date=?",
            conn, params=(asof,)
        )
        conn.close()
        if not regime_row.empty:
            probs = json.loads(regime_row['regime_probs'].iloc[0])
            r4 = probs.get('R4', 0)
            r5 = probs.get('R5', 0)
            if r4 + r5 > 0.4:
                alerts.append({
                    'level': 'CRITICAL',
                    'type': 'REGIME_SHIFT_PRESSURE',
                    'msg': f"🚨 衰退/危机体制概率合计 {(r4+r5)*100:.1f}%",
                    'metric': {'R4': r4, 'R5': r5}
                })
    except Exception:
        pass

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS liquidity_alerts (
            asof_date TEXT, level TEXT, alert_type TEXT, message TEXT, metric TEXT,
            PRIMARY KEY (asof_date, alert_type)
        )
    """)
    for a in alerts:
        conn.execute("""
            INSERT OR REPLACE INTO liquidity_alerts
            (asof_date, level, alert_type, message, metric)
            VALUES (?, ?, ?, ?, ?)
        """, (asof, a['level'], a['type'], a['msg'], json.dumps(a['metric'])))
    conn.commit()
    conn.close()

    return {'asof': asof, 'alert_count': len(alerts), 'alerts': alerts,
            'net_liq_now_b': round(net_now, 2), 'rrp_now_b': round(rrp_now, 2)}


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = check_alerts(asof)
    print(f"\n{'='*60}")
    print(f"  流动性拐点预警 - {asof}")
    print(f"{'='*60}")
    print(f"  净流动性: {result.get('net_liq_now_b', 'N/A')} 十亿美元")
    print(f"  RRP 余额: {result.get('rrp_now_b', 'N/A')} 十亿美元")
    if result['alert_count'] == 0:
        print("  ✅ 无预警信号")
    else:
        for a in result['alerts']:
            print(f"\n  [{a['level']}] {a['type']}")
            print(f"  {a['msg']}")
    print(f"{'='*60}\n")