"""engines_v2/engine_fis.py - 财政/久期供给引擎（代理版）"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engines_v2.base_engine import (
    load_pit_series, pca_reduce, classify_direction,
    save_engine_result, create_pit_table_if_missing
)

ENGINE_ID = 'FIS'

def compute_engine(asof: str) -> dict:
    create_pit_table_if_missing()
    series_ids = [
        'DEBT_TOTAL',       # 美国国债总额
        'YC30Y',            # 30Y收益率（长端）
        'YC10Y',            # 10Y收益率
    ]
    df = load_pit_series(series_ids, lookback=60)
    
    if df.empty or len(df) < 20:
        result = {'engine_id': ENGINE_ID, 'z_score': 0.0, 'direction': 'NEUTRAL',
                  'loadings': {}, 'raw': {}, 'error': f'insufficient_data len={len(df)}'}
        save_engine_result(asof, ENGINE_ID, 0.0, 'NEUTRAL', {}, {})
        return result
    
    z, loadings = pca_reduce(df, sign_anchor_col='YC30Y', sign_expected=1.0)
    direction = classify_direction(z, pos_label='SUPPLY_STRESS', neg_label='RELIEF')
    
    raw = {c: round(float(df[c].iloc[-1]), 4) for c in df.columns}
    save_engine_result(asof, ENGINE_ID, z, direction, loadings, raw)
    
    return {'engine_id': ENGINE_ID, 'z_score': z, 'direction': direction,
            'loadings': loadings, 'raw': raw}