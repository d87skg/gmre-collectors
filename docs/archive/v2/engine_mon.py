"""engines_v2/engine_mon.py - 货币紧缩引擎"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engines_v2.base_engine import (
    load_pit_series, pca_reduce, classify_direction,
    save_engine_result, create_pit_table_if_missing
)

ENGINE_ID = 'MON'

def compute_engine(asof: str) -> dict:
    create_pit_table_if_missing()
    series_ids = [
        'FEDFUNDS',         # 联邦基金利率
        'YC2Y',             # 2Y收益率
        'US_10Y_2Y_SPREAD', # 10Y-2Y曲线
    ]
    df = load_pit_series(series_ids, lookback=60)
    
    if df.empty or len(df) < 20:
        result = {'engine_id': ENGINE_ID, 'z_score': 0.0, 'direction': 'NEUTRAL',
                  'loadings': {}, 'raw': {}, 'error': f'insufficient_data len={len(df)}'}
        save_engine_result(asof, ENGINE_ID, 0.0, 'NEUTRAL', {}, {})
        return result
    
    z, loadings = pca_reduce(df, sign_anchor_col='FEDFUNDS', sign_expected=1.0)
    direction = classify_direction(z, pos_label='TIGHT', neg_label='EASING')
    
    raw = {c: round(float(df[c].iloc[-1]), 4) for c in df.columns}
    save_engine_result(asof, ENGINE_ID, z, direction, loadings, raw)
    
    return {'engine_id': ENGINE_ID, 'z_score': z, 'direction': direction,
            'loadings': loadings, 'raw': raw}