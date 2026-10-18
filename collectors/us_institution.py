import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

def get_coinbase_premium():
    """计算 Coinbase 相对 OKX 的 BTC 现货溢价"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    cb_price, okx_price = None, None
    
    # 1. 获取 Coinbase 价格
    try:
        cb_res = requests.get('https://api.coinbase.com/v2/prices/BTC-USD/spot', headers=headers, timeout=10).json()
        cb_price = float(cb_res['data']['amount'])
    except Exception as e:
        print(f"Coinbase 价格失败: {e}")

    # 2. 获取 OKX 价格 (作为对比基准，比 Binance 更稳定)
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

def main():
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    
    cb_p, okx_p, premium = get_coinbase_premium()
    if premium is not None:
        rows.append({
            'datetime': now,
            'metric': 'COINBASE_PREMIUM',
            'value': premium,
            'extra': f"CB:${cb_p:.0f} / OKX:${okx_p:.0f}"
        })
        print(f"✅ Coinbase 溢价: {premium:+.3f}%")

    bg_fr = get_bitget_fr()
    if bg_fr is not None:
        rows.append({
            'datetime': now,
            'metric': 'BITGET_FR',
            'value': bg_fr,
            'extra': 'BTC 年化'
        })
        print(f"✅ Bitget FR: {bg_fr:+.2f}% 年化")

    if rows:
        df = pd.DataFrame(rows)
        Path('data').mkdir(exist_ok=True)
        df.to_csv('data/us_institution.csv', index=False)
        print(f"已保存 {len(rows)} 条美国机构指标数据")
    else:
        print("❌ 未获取到机构数据")

if __name__ == '__main__':
    main()