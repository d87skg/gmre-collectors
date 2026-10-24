"""engines_v2/engine_liq.py - 全球流动性引擎（净流动性增强版·单位统一修复）"""
import sys, os
import sqlite3
import pandas as pd
import numpy as np
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engines_v2.base_engine import (
    pca_reduce, classify_direction, save_engine_result, create_pit_table_if_missing
)

ENGINE_ID = 'LIQ'
DB_PATH = 'data/macro.db'


def _load_single(conn, series_id, lookback=200):
    """加载单个 series，保留最近 lookback 条，去重排序"""
    for date_col in ['timestamp', 'date', 'asof_date']:
        try:
            df = pd.read_sql_query(
                f"SELECT {date_col} AS dt, value FROM observations "
                f"WHERE series_id=? ORDER BY {date_col} DESC LIMIT ?",
                conn, params=(series_id, lookback)
            )
            if not df.empty:
                df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
                df = df.dropna(subset=['dt'])
                df['dt'] = df['dt'].dt.strftime('%Y-%m-%d')
                df = df.drop_duplicates(subset=['dt'], keep='first')
                df = df.sort_values('dt')
                return df.set_index('dt')['value'].rename(series_id)
        except Exception:
            continue
    return pd.Series(dtype=float, name=series_id)


def compute_engine(asof: str) -> dict:
    create_pit_table_if_missing()

    conn = sqlite3.connect(DB_PATH)
    try:
        walcl = _load_single(conn, 'FED_WALCL', 200)   # 周频：美联储总资产（百万美元）
        tga   = _load_single(conn, 'TGA_BALANCE', 200) # 日频：财政部TGA（百万美元）
        rrp   = _load_single(conn, 'RRP_BALANCE', 200) # 日频：逆回购（十亿美元）
        dxy   = _load_single(conn, 'DXY_PROXY', 200)   # 日频：美元指数
    finally:
        conn.close()

    if len(walcl) < 5 or len(tga) < 5 or len(rrp) < 5:
        result = {'engine_id': ENGINE_ID, 'z_score': 0.0, 'direction': 'NEUTRAL',
                  'loadings': {}, 'raw': {}, 'error': 'insufficient_data'}
        save_engine_result(asof, ENGINE_ID, 0.0, 'NEUTRAL', {}, {})
        return result

    # ============ 核心改进：日频对齐 + 净流动性合成 ============
    # 1. 拼接所有序列，外连接（所有日期都保留）
    df = pd.concat([walcl, tga, rrp, dxy], axis=1).sort_index()
    # 2. 周频 WALCL 向前填充到日频；前几行反向填充
    df = df.ffill().bfill()

    # 3. 单位统一：全部转成"十亿美元"
    #    FED_WALCL: 百万美元 → 十亿美元  (÷1000)
    #    TGA_BALANCE: 百万美元 → 十亿美元 (÷1000)
    #    RRP_BALANCE: 本身就是十亿美元，不变
       # 单位统一：三个序列全是"百万美元"，统一 ÷1000 变成"十亿美元"
    df['FED_WALCL_B']   = df['FED_WALCL'] / 1000.0
    df['TGA_BALANCE_B'] = df['TGA_BALANCE'] / 1000.0
    df['RRP_BALANCE_B'] = df['RRP_BALANCE']            # RRP已是十亿美元
    df['NET_LIQ'] = df['FED_WALCL_B'] - df['TGA_BALANCE_B'] - df['RRP_BALANCE_B']

    # 4. 计算净流动性（单位：十亿美元）
    df['NET_LIQ'] = df['FED_WALCL_B'] - df['TGA_BALANCE_B'] - df['RRP_BALANCE_B']

    # 5. 只用净流动性 + 美元指数作为输入
    z_input = df[['NET_LIQ', 'DXY_PROXY']].dropna()

    if len(z_input) < 20:
        result = {'engine_id': ENGINE_ID, 'z_score': 0.0, 'direction': 'NEUTRAL',
                  'loadings': {}, 'raw': {}, 'error': 'insufficient_data'}
        save_engine_result(asof, ENGINE_ID, 0.0, 'NEUTRAL', {}, {})
        return result

    # 6. 用 DXY 作为锚定：DXY上升 = 流动性收紧 = LIQ正值
    z, loadings = pca_reduce(z_input, sign_anchor_col='DXY_PROXY', sign_expected=1.0)
    direction = classify_direction(z, pos_label='TIGHTENING', neg_label='EASING')

    # 7. 详细输出（单位统一为十亿美元）
    raw = {
        'NET_LIQ_十亿': round(float(df['NET_LIQ'].iloc[-1]), 2),
        'WALCL_十亿': round(float(df['FED_WALCL_B'].iloc[-1]), 2),
        'TGA_十亿': round(float(df['TGA_BALANCE_B'].iloc[-1]), 2),
        'RRP_十亿': round(float(df['RRP_BALANCE_B'].iloc[-1]), 2),
        'DXY': round(float(df['DXY_PROXY'].iloc[-1]), 4),
        'NET_LIQ_5d_change': round(float(df['NET_LIQ'].iloc[-1] - df['NET_LIQ'].iloc[-6]), 2) if len(df) >= 6 else 0,
        'NET_LIQ_20d_change': round(float(df['NET_LIQ'].iloc[-1] - df['NET_LIQ'].iloc[-21]), 2) if len(df) >= 21 else 0,
    }
    save_engine_result(asof, ENGINE_ID, z, direction, loadings, raw)

    return {'engine_id': ENGINE_ID, 'z_score': z, 'direction': direction,
            'loadings': loadings, 'raw': raw}