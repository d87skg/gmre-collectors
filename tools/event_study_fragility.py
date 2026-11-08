# -*- coding: utf-8 -*-
"""tools/event_study_fragility.py - Fragility事件研究验证 (v2: 动态周期与降维)"""
import sqlite3
import pandas as pd
import sys

sys.stdout.reconfigure(encoding='utf-8')
DB_PATH = 'data/macro.db'

# 🆕 修改阈值：放宽到 65，获取更多历史样本
THRESHOLD = 65

def run_event_study():
    print(f"🔍 启动 Fragility 信号事件研究 (阈值 >= {THRESHOLD})...")
    
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    
    # 1. 找出历史所有触发日
    query_frag = f"""
        SELECT asof_date, fragility_score 
        FROM fragility_engine 
        WHERE fragility_score >= {THRESHOLD}
        ORDER BY asof_date
    """
    df_frag = pd.read_sql_query(query_frag, conn)
    
    if df_frag.empty:
        print(f"⚠️ 历史中没有 Fragility >= {THRESHOLD} 的记录。")
        conn.close()
        return
        
    print(f"✅ 发现 {len(df_frag)} 个触发日:")
    print(df_frag['asof_date'].tolist())
    
    # 2. 拉取标普 500 的历史数据
    query_spx = """
        SELECT timestamp as asof_date, value as spx 
        FROM observations 
        WHERE series_id = 'SP500'
        ORDER BY timestamp
    """
    df_spx = pd.read_sql_query(query_spx, conn)
    conn.close()
    
    df_spx['asof_date'] = pd.to_datetime(df_spx['asof_date'])
    df_spx = df_spx.set_index('asof_date').sort_index()
    
    # 3. 计算后续收益 (T+1, T+3, T+5, T+10)
    horizons = [1, 3, 5, 10]
    results = {h: [] for h in horizons}
    
    for date_str in df_frag['asof_date']:
        date = pd.to_datetime(date_str)
        
        # 找到触发日及之后的收盘价
        future_data = df_spx[df_spx.index >= date]
        
        # 如果连第2天都没有，跳过
        if len(future_data) < 2:
            continue
            
        base_price = future_data.iloc[0]['spx']
        
        for h in horizons:
            # 🆕 动态判断：如果未来数据够长，就计算；不够就跳过
            if len(future_data) > h:
                future_price = future_data.iloc[h]['spx']
                ret = (future_price / base_price) - 1
                results[h].append(ret)
            
    # 4. 输出统计报告
    print(f"\n{'='*55}\n 📊 Fragility >= {THRESHOLD} 触发后的 SP500 前瞻收益\n{'='*55}")
    print(f"{'周期':<8} | {'样本数':<6} | {'平均收益':<10} | {'胜率(下跌)':<10} | {'最差表现'}")
    print("-" * 65)
    
    for h in horizons:
        rets = results[h]
        if not rets:
            print(f"T+{h:<6} | {'数据不足':<8} | {'-':<10} | {'-':<10} | {'-'}")
            continue
        
        avg_ret = sum(rets) / len(rets)
        # 胜率定义为：下跌的概率
        win_rate = sum(1 for r in rets if r < 0) / len(rets) * 100
        worst_ret = min(rets)
        
        print(f"T+{h:<6} | {len(rets):<8} | {avg_ret*100:>+8.2f}% | {win_rate:>8.1f}%   | {worst_ret*100:>+8.2f}%")

if __name__ == "__main__":
    run_event_study()