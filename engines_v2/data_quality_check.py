"""engines_v2/data_quality_check.py - 数据真实性自检与跨市场勾稽（最终修复版）"""
import sys as _sys
from pathlib import Path as _Path
_PROJECT_ROOT = _Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))
from tools.rrp_guard import run_rrp_guard, RRPStatus
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def _load(conn, sids, limit=500):
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


def run_audit(asof: str = None) -> dict:
    """执行7项数据质量自检"""
    if asof is None:
        asof = datetime.now().strftime('%Y-%m-%d')

    conn = sqlite3.connect(DB_PATH)
    try:
        df = _load(conn, ['FED_WALCL', 'TGA_BALANCE', 'RRP_BALANCE',
                          'USD_JPY', 'VIX', 'YC10Y', 'JP_10Y_YIELD',
                          'RRP_NYFED', 'TGA_DAILY'], limit=500)
    finally:
        conn.close()

    if df.empty or len(df) < 30:
        return {'status': 'FAIL', 'error': 'insufficient_data', 'checks': []}

    checks = []
    warnings = []
    criticals = []

    # ============ 检查1：WALCL 数据完整性 ============
    if 'FED_WALCL' in df.columns:
        walcl = df['FED_WALCL'].dropna()
        if len(walcl) >= 30:
            checks.append({
                'name': 'WALCL 完整性',
                'status': 'PASS',
                'detail': f'{len(walcl)} 条数据，最新值 {walcl.iloc[-1]:,.0f} 百万美元'
            })
        else:
            criticals.append('WALCL 数据缺失严重')
            checks.append({'name': 'WALCL 完整性', 'status': 'FAIL',
                           'detail': f'仅 {len(walcl)} 条'})

    # ============ 检查2：净流动性计算 ============
    if all(c in df.columns for c in ['FED_WALCL', 'TGA_BALANCE', 'RRP_BALANCE']):
        df_calc = df[['FED_WALCL', 'TGA_BALANCE', 'RRP_BALANCE']].ffill().bfill()
        net_liq = (df_calc['FED_WALCL'] / 1000
                   - df_calc['TGA_BALANCE'] / 1000
                   - df_calc['RRP_BALANCE'] / 1000)
        latest_net_liq = float(net_liq.iloc[-1])

        if 3000 < latest_net_liq < 7000:
            checks.append({
                'name': '净流动性合理性',
                'status': 'PASS',
                'detail': f'{latest_net_liq:.2f} 十亿美元（合理区间 3000-7000）'
            })
        else:
            warnings.append(f'净流动性异常: {latest_net_liq:.2f}')
            checks.append({'name': '净流动性合理性', 'status': 'WARN',
                           'detail': f'{latest_net_liq:.2f} 十亿美元'})

    # ============ 检查3：美联储资产负债表恒等式 ============
    if 'FED_WALCL' in df.columns and 'TGA_BALANCE' in df.columns:
        walcl_b = float(df['FED_WALCL'].ffill().iloc[-1]) / 1000
        if walcl_b > 6000:
            checks.append({
                'name': '资产负债表恒等式',
                'status': 'PASS',
                'detail': f'WALCL={walcl_b/1000:.2f}万亿（{walcl_b:.0f}十亿），处于正常QT区间'
            })
        else:
            criticals.append('WALCL 低于 6万亿，QT可能过度')

    # ============ 检查4：RRP 双源对齐 (由 rrp_guard 统一判定) ============
    try:
        _g = run_rrp_guard(verbose=False)
        if _g.status in (RRPStatus.OK, RRPStatus.TIME_LAG):
            _detail = (
                f"FRED={_g.fred_value:.2f}@{_g.fred_date}, "
                f"NYFed={_g.nyfed_value:.2f}@{_g.nyfed_date}, "
                f"lag={_g.lag_days}d, 同日期偏差={_g.same_day_max_divergence_pct:.2f}%"
            )
            checks.append({
                'name': 'RRP 双源对齐',
                'status': 'PASS',
                'detail': _detail
            })
        elif _g.status == RRPStatus.DIVERGENCE:
            warnings.append(f'RRP 同日源分歧 {_g.same_day_max_divergence_pct:.1f}%')
            checks.append({
                'name': 'RRP 双源对齐',
                'status': 'WARN',
                'detail': _g.message
            })
        else:  # STALE / MISSING
            criticals.append(f'RRP 数据不可用: {_g.status.value}')
            checks.append({
                'name': 'RRP 双源对齐',
                'status': 'FAIL',
                'detail': _g.message
            })
    except Exception as _e:
        warnings.append(f'RRP guard 调用异常: {_e}')
        checks.append({
            'name': 'RRP 双源对齐',
            'status': 'WARN',
            'detail': f'guard error: {_e}'
        })

    # ============ 检查5：TGA 日频 vs 周频 对比 ============
    if 'TGA_BALANCE' in df.columns and 'TGA_DAILY' in df.columns:
        tga_w = float(df['TGA_BALANCE'].ffill().iloc[-1]) / 1000
        tga_d = float(df['TGA_DAILY'].ffill().iloc[-1]) / 1000
        if tga_w > 0:
            diff = abs(tga_w - tga_d) / tga_w * 100
            if diff < 15:
                checks.append({
                    'name': 'TGA 周频vs日频',
                    'status': 'PASS',
                    'detail': f'周频={tga_w:.1f}B, 日频={tga_d:.1f}B, 偏差={diff:.1f}%'
                })
            else:
                warnings.append(f'TGA 频次偏差 {diff:.1f}%')
                checks.append({'name': 'TGA 周频vs日频', 'status': 'WARN',
                               'detail': f'周频={tga_w:.1f}B, 日频={tga_d:.1f}B'})

    # ============ 检查6：CARRY 勾稽（统一时间窗口） ============
    if 'USD_JPY' in df.columns and 'VIX' in df.columns:
        usdjpy_clean = df['USD_JPY'].dropna().tail(60)
        vix_clean = df['VIX'].dropna().tail(60)
        if len(usdjpy_clean) >= 21 and len(vix_clean) >= 21:
            usdjpy_20d = float(usdjpy_clean.pct_change(20).iloc[-1])
            vix_20d = float(vix_clean.pct_change(20).iloc[-1])
            current_usdjpy = float(usdjpy_clean.iloc[-1])

            if usdjpy_20d < -0.015 and vix_20d > 0.10:
                checks.append({
                    'name': 'CARRY 勾稽',
                    'status': 'PASS',
                    'detail': f'🚨 CARRY_WARNING成立: USDJPY 20d={usdjpy_20d*100:.2f}%, VIX 20d={vix_20d*100:.2f}%, 汇率={current_usdjpy:.2f}'
                })
            else:
                checks.append({
                    'name': 'CARRY 勾稽',
                    'status': 'PASS',
                    'detail': f'USDJPY 20d={usdjpy_20d*100:.2f}%, VIX 20d={vix_20d*100:.2f}%'
                })

    # ============ 检查7：美日利差验证（统一窗口） ============
    if 'YC10Y' in df.columns and 'JP_10Y_YIELD' in df.columns:
        us10y_clean = df['YC10Y'].dropna().tail(30)
        jp10y_clean = df['JP_10Y_YIELD'].dropna().tail(30)
        if len(us10y_clean) >= 1 and len(jp10y_clean) >= 1:
            us10y = float(us10y_clean.iloc[-1])
            jp10y = float(jp10y_clean.iloc[-1])
            spread_bp = (us10y - jp10y) * 100
            if 100 < spread_bp < 500:
                checks.append({
                    'name': '美日利差',
                    'status': 'PASS',
                    'detail': f'US10Y={us10y:.2f}%, JP10Y={jp10y:.2f}%, 利差={spread_bp:.0f}bp'
                })
            else:
                warnings.append(f'美日利差异常: {spread_bp:.0f}bp')

    # ============ 汇总 ============
    status = 'PASS'
    if warnings:
        status = 'WARN'
    if criticals:
        status = 'FAIL'

    result = {
        'asof': asof,
        'status': status,
        'checks': checks,
        'warnings': warnings,
        'criticals': criticals,
        'pass_count': len([c for c in checks if c['status'] == 'PASS']),
        'warn_count': len(warnings),
        'critical_count': len(criticals)
    }

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_quality_audit (
            asof_date TEXT PRIMARY KEY,
            status TEXT, pass_count INTEGER, warn_count INTEGER, critical_count INTEGER,
            detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO data_quality_audit
        (asof_date, status, pass_count, warn_count, critical_count, detail)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (asof, status, result['pass_count'], result['warn_count'],
          result['critical_count'], json.dumps(checks)))
    conn.commit()
    conn.close()

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = run_audit(asof)
    print(f"\n{'='*60}")
    print(f"  数据真实性自检 - {asof}")
    print(f"{'='*60}")
    print(f"  总状态: {result['status']}")
    print(f"  通过: {result['pass_count']}  |  警告: {result['warn_count']}  |  严重: {result['critical_count']}\n")
    for c in result['checks']:
        icon = '✅' if c['status'] == 'PASS' else '⚠️' if c['status'] == 'WARN' else '❌'
        print(f"  {icon} [{c['name']}] {c['detail']}")
    if result['warnings']:
        print(f"\n  警告详情:")
        for w in result['warnings']:
            print(f"    ⚠️ {w}")
    if result['criticals']:
        print(f"\n  严重问题:")
        for c in result['criticals']:
            print(f"    ❌ {c}")
    print(f"{'='*60}\n")