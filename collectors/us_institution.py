import requests
import pandas as pd
import os
import csv
from datetime import datetime, timezone
from pathlib import Path

def get_coinbase_premium():
    """计算 Coinbase 相对 OKX 的 BTC 现货溢价"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    cb_price, okx_price = None, None
    
    # 1. 获取 Coinbase 价格（带备用接口）
    try:
        cb_res = requests.get('https://api.coinbase.com/v2/prices/BTC-USD/spot', headers=headers, timeout=10).json()
        if 'data' in cb_res:
            cb_price = float(cb_res['data']['amount'])
        else:
            # 如果没拿到，尝试备用接口
            cb_res2 = requests.get('https://api.exchange.coinbase.com/products/BTC-USD/ticker', headers=headers, timeout=10).json()
            cb_price = float(cb_res2['price'])
    except Exception as e:
        print(f"Coinbase 价格失败: {e}")

    # 2. 获取 OKX 价格
    try:
        okx_res = requests.get('https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT', headers=headers, timeout=10).json()
        if okx_res.get('code') == '0':
            okx_price = float(okx_res['data'][0]['last'])
    except Exception as e:
        print(f"OKX 价格失败: {e}")

    # 3. 计算溢价
    if cb_price and okx_price:
        premium = ((cb_price - okx_price) / okx_price) * 100
        return cb_price, okx_price, premium
        
    return None, None, None

def get_bitget_fr():
    """获取 Bitget BTC 永续合约资金费率"""
    try:
        url = 'https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=BTCUSDT&productType=USDT-FUTURES'
        res = requests.get(url, timeout=10).json()
        if res.get('code') == '00000':
            fr = float(res['data'][0]['fundingRate'])
            return fr * 100 * 24 * 365
    except Exception as e:
        print(f"Bitget FR 抓取失败: {e}")
    return None

def get_binance_ratios():
    """尝试从 binance_sentiment.csv 读取当天的多空比"""
    retail_ratio, top_ratio = None, None
    p = Path('data/binance_sentiment.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            for _, r in df.iterrows():
                if r['metric'] == 'RETAIL_LONG_SHORT_RATIO':
                    retail_ratio = float(r['value'])
                elif r['metric'] == 'TOP_LONG_SHORT_RATIO':
                    top_ratio = float(r['value'])
        except Exception as e:
            print(f"读取 Binance 多空比失败: {e}")
    return retail_ratio, top_ratio

def main():
    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')
    rows = []
    
    # 1. 抓取独立数据
    cb_p, okx_p, premium = get_coinbase_premium()
    if premium is not None:
        rows.append({
            'datetime': now_dt.isoformat(),
            'metric': 'COINBASE_PREMIUM',
            'value': premium,
            'extra': f"CB:${cb_p:.0f} / OKX:${okx_p:.0f}"
        })
        print(f"✅ Coinbase 溢价: {premium:+.3f}%")

    bg_fr = get_bitget_fr()
    if bg_fr is not None:
        rows.append({
            'datetime': now_dt.isoformat(),
            'metric': 'BITGET_FR',
            'value': bg_fr,
            'extra': 'BTC 年化'
        })
        print(f"✅ Bitget FR: {bg_fr:+.2f}% 年化")

    # 保存当天的 us_institution.csv (用于飞书展示)
    if rows:
        df = pd.DataFrame(rows)
        Path('data').mkdir(exist_ok=True)
        df.to_csv('data/us_institution.csv', index=False)
        print(f"已保存 {len(rows)} 条美国机构指标数据")
    else:
        print("❌ 未获取到机构数据")
    
    # 2. 获取 Binance 多空比 (依赖 binance_sentiment.py)
    retail_ratio, top_ratio = get_binance_ratios()

    # 3. 追加到历史长河文件中 (crypto_micro.csv)
    csv_path = 'data/crypto_micro.csv'
    file_exists = os.path.isfile(csv_path)
    
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # 如果文件不存在，先写表头
        if not file_exists:
            writer.writerow(['datetime', 'coinbase_premium', 'bitget_funding', 'retail_long_short', 'top_long_short'])
        
        # 写入当天的数据（如果某个数据抓取失败，填 None，在 csv 里是空值）
        writer.writerow([
            now_str, 
            f"{premium:.4f}" if premium is not None else '',
            f"{bg_fr:.4f}" if bg_fr is not None else '',
            retail_ratio if retail_ratio is not None else '',
            top_ratio if top_ratio is not None else ''
        ])
    print(f"✅ 历史数据已成功追加到 {csv_path}")

if __name__ == '__main__':
    main()