"""
FRED 宏观指标（扩展版） - 强制重试与降级版
"""
import os
import time
import requests
import pandas as pd
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env（写死绝对路径）
load_dotenv(r'D:\HGZC\.env')

OUT = Path('data/fred_macro.csv')
BASE = 'https://api.stlouisfed.org/fred/series/observations'
API_KEY = os.environ.get('FRED_API_KEY')

SERIES = [
    # 原 11 系列
    'WRESBAL', 'CPF3M', 'TB3MS', 'THREEFYTP10', 'BAMLH0A0HYM2',
    'BAMLC0A0CM', 'RIFSPPNA2P2D60NB', 'DGS2', 'DGS10', 'DGS30', 'DRCRELEXFACBS',
    # 新增 10 系列
    'DFII10', 'T5YIE', 'T10YIE', 'BAMLH0A1HYBB', 'BAMLH0A2HYB',
    'BAMLH0A3HYC', 'BAMLC0A1CAAA', 'BAMLC0A4CBBB', 'T10Y3M', 'DRTSCILM',
    # 通胀 + 就业（基础）
    'CPIAUCSL', 'CPILFESL', 'PCEPI', 'PCEPILFE', 'PAYEMS', 'UNRATE', 'ICSA',
    # 通胀分项（看粘性从哪来）
    'CPIENGSL', 'CPIFABSL', 'CUSR0000SAH1', 'CUSR0000SASLE',
    # 工资与预期（验证核心通胀）
    'CES0500000003', 'ECIALLCIV', 'MICH',
    # 景气度（交叉验证非农）
    'NAPM', 'NAPMNOI', 'MANEMP', 'UMCSENT', 'IORB',
]

def fetch(series_id, days=500, retries=3):
    """核心改造：15秒超时，3次重试，失败后强制打印红字并返回空列表"""
    start = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
    params = {
        'series_id': series_id,
        'api_key': API_KEY,
        'file_type': 'json',
        'observation_start': start,
    }
    
    for attempt in range(retries):
        try:
            # 1. 缩短超时时间为 15 秒
            r = requests.get(BASE, params=params, timeout=15)
            if r.status_code == 500:
                print(f'  ⚠️ {series_id} 500 服务器错误，重试 {attempt+1}/{retries}...')
                time.sleep(3)
                continue
            r.raise_for_status()
            data = r.json()
            if 'observations' not in data:
                print(f'  ⚠️ {series_id} 返回异常格式，重试 {attempt+1}/{retries}...')
                time.sleep(3)
                continue
                
            rows = []
            for item in data['observations']:
                if item['value'] == '.':
                    continue
                rows.append({
                    'date': item['date'],
                    'series': series_id,
                    'value': float(item['value']),
                })
            return rows
        except Exception as e:
            if attempt < retries - 1:
                print(f'  ⚠️ {series_id} 请求失败/超时 ({str(e)[:30]})，重试 {attempt+1}/{retries}...')
                time.sleep(3)
            else:
                # 2. 核心改造：彻底失败时的醒目报警
                print(f'  🔴 [警告] {series_id} 连续 {retries} 次请求失败！跳过该指标，今日数据未更新。')
    
    return [] # 返回空列表，防止异常抛出导致整个程序崩溃

def main():
    if not API_KEY:
        print('❌ 缺 FRED_API_KEY')
        sys.exit(1)

    all_rows = []
    for sid in SERIES:
        # 直接调用 fetch，内部已经处理了重试和报警
        rows = fetch(sid)
        if len(rows) > 0:
            print(f'  ✅ {sid}: {len(rows)} 条')
            all_rows.extend(rows)

    if not all_rows:
        print('❌ 致命错误: 所有数据均拉取失败，放弃本次写入。')
        sys.exit(1)

    df_new = pd.DataFrame(all_rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'series'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['date', 'series'])
    df.to_csv(OUT, index=False)
    print(f'✅ 已保存: {OUT} ({len(df)} 行)')

if __name__ == '__main__':
    main()