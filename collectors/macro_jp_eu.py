# collectors/macro_jp_eu.py
import requests
import pandas as pd
import sqlite3
import io

DB_PATH = 'data/macro.db'

# 数据源映射 (FRED CSV ID -> 本地 series_id)
SERIES_MAP = {
    'IRLTLT01JPM156N': 'JP_10Y',        # 日本 10年期国债收益率 (月度)
    'FPCPITOTLZGJPN': 'JP_CPI_YOY',     # ✅ 换成世界银行日本年度通胀率 (年度)
    'IRLTLT01DEM156N': 'DE_10Y',        # 德国 10年期国债收益率 (月度)
    'FPCPITOTLZGEMU': 'EU_HICP_YOY',    # ✅ 换成世界银行欧元区年度通胀率 (年度)
    'DEXJPUS': 'USD_JPY',               # 美元/日元 (日度)
    'DEXUSEU': 'EUR_USD'                # 欧元/美元 (日度)
}

def fetch_and_save(fred_id, local_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ['date', 'value']
        df = df[df['value'] != '.']
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("DELETE FROM observations WHERE series_id = ?", (local_id,))
        
        count = 0
        for _, row in df.iterrows():
            try:
                c.execute("""
                    INSERT INTO observations (series_id, timestamp, value, source, retrieved_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (local_id, str(row['date']), float(row['value']), f'fred_{fred_id}'))
                count += 1
            except Exception:
                pass
        
        conn.commit()
        conn.close()
        print(f"✅ {local_id:<15} (源:{fred_id}) 更新 {count} 条，最新: {df.iloc[-1]['date']} = {df.iloc[-1]['value']}")
    except Exception as e:
        print(f"❌ {local_id} 拉取失败: {e}")

def main():
    print("⏳ 开始抓取日本与欧洲宏观数据...")
    for fred_id, local_id in SERIES_MAP.items():
        fetch_and_save(fred_id, local_id)
    print("🎉 日欧宏观数据采集完成！")

if __name__ == '__main__':
    main()