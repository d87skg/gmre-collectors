# -*- coding: utf-8 -*-
"""tools/audit_factor_correlation.py - 宏观引擎共线性体检"""
import sqlite3
import pandas as pd
import numpy as np
import sys

sys.stdout.reconfigure(encoding='utf-8')
DB_PATH = 'data/macro.db'

def audit_factors():
    print("🔍 启动因子体检：检查宏观引擎的共线性...")
    
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    query = """
        SELECT asof_date, engine_id, z_score 
        FROM engine_latents 
        WHERE asof_date >= date('now', '-250 days')
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print("⚠️ 没有找到 engine_latents 数据。")
        return
        
    # 转置为：行是日期，列是引擎
    pivot = df.pivot_table(index='asof_date', columns='engine_id', values='z_score')
    pivot = pivot.dropna(how='all')
    
    print(f"\n📊 参与体检的引擎: {list(pivot.columns)}")
    
    # 1. 计算 Pearson 相关系数矩阵
    corr = pivot.corr()
    print(f"\n{'='*40}\n 🔗 相关性矩阵 (Pearson)\n{'='*40}")
    print(corr.round(2).to_string())
    
    # 2. 找出高度相关的引擎对 (大于 0.7 或 小于 -0.7)
    print(f"\n🚨 高度相关预警 (>|0.7|):")
    for i in range(len(corr.columns)):
        for j in range(i+1, len(corr.columns)):
            col1, col2 = corr.columns[i], corr.columns[j]
            val = corr.iloc[i, j]
            if abs(val) >= 0.7:
                print(f"  - {col1} 与 {col2}: {val:+.2f} (存在严重冗余)")
                
    # 3. 计算 PCA (主成分分析)
    # 标准化
    pivot_norm = (pivot - pivot.mean()) / pivot.std()
    # 协方差矩阵的特征值
    cov_matrix = pivot_norm.cov()
    eigenvalues, _ = np.linalg.eig(cov_matrix)
    # 解释方差比例
    explained_var = eigenvalues / eigenvalues.sum()
    
    print(f"\n{'='*40}\n 🧬 PCA 主成分分析\n{'='*40}")
    print(f"  - PC1 解释了 {explained_var[0]*100:.1f}% 的方差")
    if len(explained_var) > 1:
        print(f"  - PC2 解释了 {explained_var[1]*100:.1f}% 的方差")
        print(f"  - PC1 + PC2 合计解释了 {(explained_var[0]+explained_var[1])*100:.1f}% 的方差")
    
    if (explained_var[0] + explained_var[1]) > 0.75:
        print("  🚨 警告：前两个主成分解释力超过 75%，说明你的引擎实际上只有 2 个独立维度（风险偏好轴+流动性轴），其余均在重复计票！")
    else:
        print("  ✅ 还不错：宏观引擎提供的信息相对独立。")

if __name__ == "__main__":
    audit_factors()