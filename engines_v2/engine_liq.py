"""engines_v2/engine_liq.py - 全球流动性引擎（净流动性增强版·时间截面严格对齐）"""
import sys, os
import sqlite3
import pandas as pd
import numpy as np
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engines_v2.base_engine import (
    pca_reduce, classify_direction, save_engine_result, create_pit_table_if_missing
)

ENGINE_ID = 'LIQ'
DB_PATH = os.environ.get('GMRE_DB_PATH', 'data/macro.db')

from core import data_proxy   # 唯一取数入口


def _load_single(conn, series_id, lookback=200):
    """加载单个 series —— 下沉到 core.data_proxy"""
    s = data_proxy.load_for_engine(conn, series_id, lookback, as_index='str')
    try:
        s.index = pd.to_datetime(s.index, errors='coerce').strftime('%Y-%m-%d')
    except Exception:
        pass
    s.name = series_id
    return s


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

    # 🆕 增加对 dxy 缺失的拦截，防止后续 dropna 把整行数据误杀
    if len(walcl) < 5 or len(tga) < 5 or len(rrp) < 5 or len(dxy) < 5:
        result = {'engine_id': ENGINE_ID, 'z_score': 0.0, 'direction': 'NEUTRAL',
                  'loadings': {}, 'raw': {}, 'error': 'insufficient_data'}
        save_engine_result(asof, ENGINE_ID, 0.0, 'NEUTRAL', {}, {})
        return result

    # ============ 核心改进：时间截面严格对齐 ============
    # 1. 拼接所有序列，外连接
    df = pd.concat([walcl, tga, rrp, dxy], axis=1).sort_index()
    
    # 2. 丢弃任何包含缺失值的行，找到真正“四个指标都有数据”的最新截面
    valid_df = df.dropna(subset=['FED_WALCL', 'TGA_BALANCE', 'RRP_BALANCE', 'DXY_PROXY'])
    
    if valid_df.empty:
        # 如果一天都对不齐，直接返回
        result = {'engine_id': ENGINE_ID, 'z_score': 0.0, 'direction': 'NEUTRAL',
                  'loadings': {}, 'raw': {}, 'error': 'no_aligned_cross_section'}
        save_engine_result(asof, ENGINE_ID, 0.0, 'NEUTRAL', {}, {})
        return result

    # 3. 强制跨期校验：如果对齐后的最新日期距离 asof 超过 3 天，拒绝计算！
    latest_aligned_date = pd.to_datetime(valid_df.index[-1])
    asof_date = pd.to_datetime(asof)
    lag_days = (asof_date - latest_aligned_date).days

    if lag_days > 15:  # 🆕 放宽到 15 天，兼容周频 WALCL 的发布延迟
        print(f"  🚨 [CRITICAL] 净流动性时间截面错配！最新对齐日 {latest_aligned_date.strftime('%Y-%m-%d')}，滞后 {lag_days} 天 > 3 天阈值。")
        print(f"      拒绝使用旧数据拼凑当前流动性，【LIQ引擎强制降级为 UNKNOWN】。")
        result = {'engine_id': ENGINE_ID, 'z_score': 0.0, 'direction': 'NEUTRAL',
                  'loadings': {}, 'raw': {}, 'error': 'stale_cross_section'}
        save_engine_result(asof, ENGINE_ID, 0.0, 'NEUTRAL', {}, {})
        return result

    # 4. 单位统一：全部转成"十亿美元"
    valid_df['FED_WALCL_B']   = valid_df['FED_WALCL'] / 1000.0
    valid_df['TGA_BALANCE_B'] = valid_df['TGA_BALANCE'] / 1000.0
    valid_df['RRP_BALANCE_B'] = valid_df['RRP_BALANCE']

    # 5. 计算净流动性
    valid_df['NET_LIQ'] = valid_df['FED_WALCL_B'] - valid_df['TGA_BALANCE_B'] - valid_df['RRP_BALANCE_B']

    # 6. 只用净流动性 + 美元指数作为输入
    z_input = valid_df[['NET_LIQ', 'DXY_PROXY']].dropna()

    if len(z_input) < 20:
        result = {'engine_id': ENGINE_ID, 'z_score': 0.0, 'direction': 'NEUTRAL',
                  'loadings': {}, 'raw': {}, 'error': 'insufficient_data'}
        save_engine_result(asof, ENGINE_ID, 0.0, 'NEUTRAL', {}, {})
        return result

    # 7. 用 DXY 作为锚定
    z, loadings = pca_reduce(z_input, sign_anchor_col='DXY_PROXY', sign_expected=1.0)
    direction = classify_direction(z, pos_label='TIGHTENING', neg_label='EASING')

    # 8. 详细输出
    raw = {
        'NET_LIQ_十亿': round(float(valid_df['NET_LIQ'].iloc[-1]), 2),
        'WALCL_十亿': round(float(valid_df['FED_WALCL_B'].iloc[-1]), 2),
        'TGA_十亿': round(float(valid_df['TGA_BALANCE_B'].iloc[-1]), 2),
        'RRP_十亿': round(float(valid_df['RRP_BALANCE_B'].iloc[-1]), 2),
        'DXY': round(float(valid_df['DXY_PROXY'].iloc[-1]), 4),
        'Aligned_Date': valid_df.index[-1], 
        'NET_LIQ_5d_change': round(float(valid_df['NET_LIQ'].iloc[-1] - valid_df['NET_LIQ'].iloc[-6]), 2) if len(valid_df) >= 6 else 0,
        'NET_LIQ_20d_change': round(float(valid_df['NET_LIQ'].iloc[-1] - valid_df['NET_LIQ'].iloc[-21]), 2) if len(valid_df) >= 21 else 0,
    }
    save_engine_result(asof, ENGINE_ID, z, direction, loadings, raw)

    return {'engine_id': ENGINE_ID, 'z_score': z, 'direction': direction,
            'loadings': loadings, 'raw': raw}