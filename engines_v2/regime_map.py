"""engines_v2/regime_map.py - GMS 宏观体制映射"""
import sqlite3
import numpy as np
import pandas as pd
import json
from datetime import datetime

DB_PATH = 'data/macro.db'

# R0-R5 原型坐标（后续可用马尔可夫训练优化）
REGIME_PROTOTYPES = {
    'R0': {'INF': 0.0, 'MON': 0.0, 'FIS': 0.0, 'LIQ': 0.0, 'RISK': 0.0},
    'R1': {'INF': 2.0, 'MON': 1.5, 'FIS': 1.0, 'LIQ': 1.0, 'RISK': 0.5},
    'R2': {'INF': 2.0, 'MON': 1.0, 'FIS': 2.0, 'LIQ': 1.5, 'RISK': 1.0},
    'R3': {'INF': 0.5, 'MON': 2.0, 'FIS': 1.0, 'LIQ': 1.0, 'RISK': 2.0},
    'R4': {'INF': -1.5,'MON': -1.0,'FIS': 0.0, 'LIQ': -2.0,'RISK': 2.5},
    'R5': {'INF': 0.0, 'MON': -0.5,'FIS': 2.0, 'LIQ': 2.5, 'RISK': 3.0},
}

REGIME_NAMES = {
    'R0': 'Mild Recovery',
    'R1': 'Overheating',
    'R2': 'Stagflation',
    'R3': 'Recession Warning',
    'R4': 'Deep Recession',
    'R5': 'Systemic Liquidity Crisis',
}

def load_latents(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT engine_id, z_score FROM engine_latents WHERE asof_date=?",
        conn, params=(asof,)
    )
    conn.close()
    return dict(zip(df['engine_id'], df['z_score']))

def map_to_regime(latents: dict) -> dict:
    keys = ['INF', 'MON', 'FIS', 'LIQ', 'RISK']
    vector = np.array([latents.get(k, 0.0) for k in keys])
    
    distances = {}
    for label, proto in REGIME_PROTOTYPES.items():
        proto_vec = np.array([proto[k] for k in keys])
        distances[label] = float(np.linalg.norm(vector - proto_vec))
    
    temp = 1.5
    scores = np.array([np.exp(-d / temp) for d in distances.values()])
    probs = scores / scores.sum()
    prob_dict = {k: round(float(v), 4) for k, v in zip(distances.keys(), probs)}
    
    best_label = max(prob_dict, key=prob_dict.get)
    return {
        'regime_label': best_label,
        'regime_name': REGIME_NAMES[best_label],
        'regime_probs': prob_dict,
        'confidence': prob_dict[best_label],
    }

def save_regime(asof: str, latents: dict, result: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gms_regimes (
            asof_date TEXT PRIMARY KEY,
            inf REAL, mon REAL, fis REAL, liq REAL, risk REAL,
            regime_label TEXT, regime_name TEXT,
            regime_probs TEXT, confidence REAL
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO gms_regimes 
        (asof_date, inf, mon, fis, liq, risk, regime_label, regime_name, regime_probs, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        asof,
        latents.get('INF', 0.0), latents.get('MON', 0.0),
        latents.get('FIS', 0.0), latents.get('LIQ', 0.0),
        latents.get('RISK', 0.0),
        result['regime_label'], result['regime_name'],
        json.dumps(result['regime_probs']), result['confidence']
    ))
    conn.commit()
    conn.close()

def run(asof: str) -> dict:
    latents = load_latents(asof)
    if not latents:
        print(f"⚠️ {asof} 没有引擎输出，请先运行引擎")
        return {}
    result = map_to_regime(latents)
    save_regime(asof, latents, result)
    return result

if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = run(asof)
    print(json.dumps(result, indent=2, ensure_ascii=False))