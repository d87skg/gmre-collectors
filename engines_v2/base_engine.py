"""engines_v2/base_engine.py - 公共工具（最终修复版）"""
import sqlite3
import pandas as pd
import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

DB_PATH = 'data/macro.db'
LOOKBACK = 60

def _normalize_date_col(df, col):
    if df.empty:
        return df
    s = df[col]
    if pd.api.types.is_numeric_dtype(s):
        if s.max() > 1e12:
            df[col] = pd.to_datetime(s, unit='ms')
        else:
            df[col] = pd.to_datetime(s, unit='s')
    else:
        df[col] = pd.to_datetime(s, errors='coerce')
    df[col] = df[col].dt.strftime('%Y-%m-%d')
    return df

def _query_series(conn, series_ids, lookback):
    """逐个series独立查询，避免SQLite字符串排序导致数据被某一系列占满"""
    
    # 1. 优先尝试 pit_observations
    try:
        placeholders = ','.join(['?'] * len(series_ids))
        df = pd.read_sql_query(
            f"""SELECT asof_date, series_id, value FROM pit_observations
                WHERE series_id IN ({placeholders})""",
            conn, params=series_ids
        )
        if not df.empty:
            return df, 'pit_observations'
    except Exception:
        pass
    
    # 2. Fallback: observations，每个series单独查最近 lookback 条
    for date_col in ['timestamp', 'date', 'asof_date', 'datetime', 'published_at']:
        frames = []
        try:
            for sid in series_ids:
                df_sid = pd.read_sql_query(
                    f"""SELECT {date_col} AS raw_date, value FROM observations
                        WHERE series_id = ?
                        ORDER BY {date_col} DESC LIMIT ?""",
                    conn, params=(sid, lookback)
                )
                if not df_sid.empty:
                    df_sid['series_id'] = sid
                    frames.append(df_sid)
            
            if frames:
                df = pd.concat(frames, ignore_index=True)
                df = _normalize_date_col(df, 'raw_date')
                df = df.rename(columns={'raw_date': 'asof_date'})
                # 同一天多条时保留最后一条
                df = df.drop_duplicates(subset=['asof_date', 'series_id'], keep='last')
                return df, f'observations.{date_col}'
        except Exception:
            continue
    
    return pd.DataFrame(), 'none'
def load_pit_series(series_ids, lookback=LOOKBACK):
    conn = sqlite3.connect(DB_PATH)
    try:
        df, source = _query_series(conn, series_ids, lookback)
    finally:
        conn.close()
    
    if df.empty:
        return pd.DataFrame()
    
    pivot = df.pivot_table(index='asof_date', columns='series_id', values='value')
    return pivot.sort_index()

def pca_reduce(df, sign_anchor_col=None, sign_expected=1.0):
    """稳健版：每个series独立算Z-score，再横向拼接PCA"""
    if df.empty or len(df) < 5:
        return 0.0, {}
    
    # 步骤1：每个series独立做20日滚动Z-score（不要求日期对齐）
    z_frames = {}
    for col in df.columns:
        s = df[col].dropna()
        if len(s) < 20:
            continue
        z = (s - s.rolling(20).mean()) / s.rolling(20).std()
        z_frames[col] = z
    
    if not z_frames:
        return 0.0, {}
    
    # 步骤2：横向拼接（index对齐，NaN自动填充）
    z_df = pd.DataFrame(z_frames).dropna(how='all')
    if len(z_df) < 5:
        return 0.0, {}
    
    # 步骤3：逐行降级填充NaN
    z_df = z_df.ffill().bfill().fillna(0.0)
    
    # 步骤4：PCA
    try:
        scaler = StandardScaler()
        z_scaled = scaler.fit_transform(z_df.values)
        pca = PCA(n_components=1)
        pc1 = pca.fit_transform(z_scaled).flatten()
        
        if sign_anchor_col and sign_anchor_col in z_df.columns:
            idx = list(z_df.columns).index(sign_anchor_col)
            actual = pca.components_[0][idx]
            if actual * sign_expected < 0:
                pc1 = -pc1
                pca.components_[0] = -pca.components_[0]
        
        std_pc = pc1.std() if pc1.std() > 0 else 1.0
        z = float(np.clip(pc1[-1] / std_pc, -3.0, 3.0))
        loadings = {c: round(float(v), 4) for c, v in zip(z_df.columns, pca.components_[0])}
        return z, loadings
    except Exception:
        # 最终降级：简单平均
        latest = z_df.iloc[-1]
        if sign_anchor_col and sign_anchor_col in latest.index:
            if latest[sign_anchor_col] * sign_expected < 0:
                latest = -latest
        return float(np.clip(latest.mean(), -3.0, 3.0)), {c: 1.0/len(latest) for c in latest.index}
def classify_direction(z, pos_label='SHOCK', neg_label='EASING', mid_label='NEUTRAL', thresh=1.5):
    if z > thresh: return pos_label
    if z < -thresh: return neg_label
    return mid_label

def save_engine_result(asof, engine_id, z, direction, loadings, raw):
    import json
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engine_latents (
            asof_date TEXT, engine_id TEXT, z_score REAL,
            direction TEXT, loadings TEXT, raw_metrics TEXT,
            PRIMARY KEY (asof_date, engine_id)
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO engine_latents 
        (asof_date, engine_id, z_score, direction, loadings, raw_metrics)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (asof, engine_id, z, direction, json.dumps(loadings), json.dumps(raw)))
    conn.commit()
    conn.close()

def create_pit_table_if_missing():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pit_observations (
            series_id TEXT, asof_date TEXT, publish_date TEXT,
            value REAL,
            PRIMARY KEY (series_id, asof_date, publish_date)
        )
    """)
    conn.commit()
    conn.close()