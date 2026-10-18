import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

def get_coinbase_premium():
    """计算 Coinbase 相对 Binance 的 BTC 现货溢价（加固防错版）"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    cb_price, bn_price = None, None
    
    # 1. 获取 Coinbase 价格（改用最稳定的 v2 接口，带回退）
    try:
        cb_res = requests.get('https://api.coinbase.com/v2/prices/BTC-USD/spot', headers=headers, timeout=10).json()
        cb_price = float(cb_res['data']['amount'])
    except Exception as e:
        print(f"Coinbase v2 失败，尝试备用接口: {e}")
        try:
            cb_res = requests.get('https://api.exchange.coinbase.com/products/BTC-USD/ticker', headers=headers, timeout=10).json()
            cb_price = float(cb_res['price'])
        except Exception as e2:
            print(f"Coinbase 备用接口也失败: {e2}")

    # 2. 获取 Binance 价格
    try:
        bn_res = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', headers=headers, timeout=10).json()
        bn_price = float(bn_res['price'])
    except Exception as e:
        print(f"Binance 价格抓取失败: {e}")

    # 3. 计算溢价
    if cb_price and bn_price:
        premium = ((cb_price - bn_price) / bn_price) * 100
        return cb_price, bn_price, premium
        
    return None, None, None

def get_bitget_fr():
    """获取 Bitget BTC 永续合约资金费率"""
    try:
        url = 'https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=BTCUSDT&productType=USDT-FUTURES'
        res = requests.get(url, timeout=10).json()
        if res.get('code') == '00000':
            fr = float(res['data'][0]['fundingRate'])
            return fr * 100 * 24 * 365 # 转换为年化
    except Exception as e:
        print(f"Bitget FR 抓取失败: {e}")
    return None

def main():
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    
    # 1. 抓取 Coinbase 溢价
    cb_p, bn_p, premium = get_coinbase_premium()
    if premium is not None:
        rows.append({
            'datetime': now,
            'metric': 'COINBASE_PREMIUM',
            'value': premium,
            'extra': f"CB:${cb_p:.0f} / BN:${bn_p:.0f}"
        })
        print(f"✅ Coinbase 溢价: {premium:+.3f}%")

    # 2. 抓取 Bitget FR
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