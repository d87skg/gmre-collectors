# collectors/macro_cn.py
import akshare as ak
import pandas as pd
import sqlite3
from datetime import datetime

DB_PATH = 'data/macro.db'

def save_to_db(series_id, df, date_col, value_col):
    """通用入库函数"""
    if df.empty or date_col not in df.columns or value_col not in df.columns:
        print(f"⚠️ {series_id} 数据格式不匹配或为空")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    count = 0
    for _, row in df.iterrows():
        try:
            # 将日期统一转为 YYYY-MM-DD 格式
            dt = pd.to_datetime(row[date_col]).strftime('%Y-%m-%d')
            val = float(row[value_col])
            
            cursor.execute("""
                INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (series_id, dt, val, 'akshare_cn'))
            count += 1
        except Exception:
            pass
            
    conn.commit()
    conn.close()
    print(f"✅ {series_id}: 成功更新 {count} 条数据")

def fetch_cn_macro():
    print("⏳ 开始抓取中国宏观数据...")
    
    # 1. 货币供应量 (M1, M2) - 用于计算剪刀差
    try:
        df_money = ak.macro_china_money_supply()
        # 提取 M1 同比和 M2 同比 (akshare的列名可能变化，通常包含"月份", "货币和准货币(M2)-同比增长", "货币(M1)-同比增长")
        # 这里我们做一下适配处理
        date_col = '月份'
        m2_col = [c for c in df_money.columns if 'M2' in c and '同比' in c]
        m1_col = [c for c in df_money.columns if 'M1' in c and '同比' in c]
        
        if m1_col and m2_col:
            save_to_db('CN_M1_YOY', df_money, date_col, m1_col[0])
            save_to_db('CN_M2_YOY', df_money, date_col, m2_col[0])
    except Exception as e:
        print(f"❌ M1/M2 获取失败: {e}")

    # 2. 制造业 PMI
    try:
        df_pmi = ak.macro_china_pmi_yearly()
        # akshare返回的通常是 日期 和 今值
        if not df_pmi.empty:
            save_to_db('CN_PMI_MFG', df_pmi, '日期', '今值')
    except Exception as e:
        print(f"❌ PMI 获取失败: {e}")

    # 3. CPI 和 PPI
    try:
        df_cpi = ak.macro_china_cpi_yearly()
        if not df_cpi.empty:
            save_to_db('CN_CPI_YOY', df_cpi, '日期', '今值')
            
        df_ppi = ak.macro_china_ppi_yearly()
        if not df_ppi.empty:
            save_to_db('CN_PPI_YOY', df_ppi, '日期', '今值')
    except Exception as e:
        print(f"❌ CPI/PPI 获取失败: {e}")

    # 4. 中国 10年期国债收益率
    try:
        df_bond = ak.bond_zh_us_rate()
        # 只要 中国国债收益率10年
        save_to_db('CN_10Y_YIELD', df_bond, '日期', '中国国债收益率10年')
    except Exception as e:
        print(f"❌ 中国10Y国债获取失败: {e}")

if __name__ == '__main__':
    fetch_cn_macro()