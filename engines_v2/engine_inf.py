"""engines_v2/engine_inf.py - 通胀冲击引擎"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engines_v2.base_engine import (
    load_pit_series, pca_reduce, classify_direction,
    save_engine_result, create_pit_table_if_missing
)

ENGINE_ID = 'INF'

def compute_engine(asof: str) -> dict:
    create_pit_table_if_missing()
    series_ids = [
        'CPIAUCSL',      # CPI 季调
        'US_CPI_YOY',    # 美国CPI同比
        'WB_INFLATION',  # 世界银行通胀
    ]
    df = load_pit_series(series_ids, lookback=60)
    
    if df.empty or len(df) < 20:
        result = {'engine_id': ENGINE_ID, 'z_score': 0.0, 'direction': 'NEUTRAL',
                  'loadings': {}, 'raw': {}, 'error': f'insufficient_data len={len(df)}'}
        save_engine_result(asof, ENGINE_ID, 0.0, 'NEUTRAL', {}, {})
        return result
    
    z, loadings = pca_reduce(df, sign_anchor_col='CPIAUCSL', sign_expected=1.0)
    direction = classify_direction(z, pos_label='SHOCK', neg_label='DEFLATION')
    
    raw = {c: round(float(df[c].iloc[-1]), 4) for c in df.columns}
    save_engine_result(asof, ENGINE_ID, z, direction, loadings, raw)
    
    return {'engine_id': ENGINE_ID, 'z_score': z, 'direction': direction,
            'loadings': loadings, 'raw': raw}