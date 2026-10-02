"""
测试 Binance 各域名在 GitHub Actions 美国 IP 下的可达性
"""
import requests

TESTS = [
    ('fapi.binance.com 合约',     'https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT'),
    ('fapi1.binance.com 合约',    'https://fapi1.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT'),
    ('fapi2.binance.com 合约',    'https://fapi2.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT'),
    ('dapi.binance.com 交割',     'https://dapi.binance.com/dapi/v1/time'),
    ('data-api.binance.vision',   'https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT'),
    ('api.binance.us',            'https://api.binance.us/api/v3/ticker/price?symbol=BTCUSDT'),
    ('fapi.binance.us 合约',      'https://fapi.binance.us/fapi/v1/premiumIndex?symbol=BTCUSDT'),
    ('api1.binance.com',          'https://api1.binance.com/api/v3/ticker/price?symbol=BTCUSDT'),
    ('api2.binance.com',          'https://api2.binance.com/api/v3/ticker/price?symbol=BTCUSDT'),
    ('api3.binance.com',          'https://api3.binance.com/api/v3/ticker/price?symbol=BTCUSDT'),
]

for name, url in TESTS:
    try:
        r = requests.get(url, timeout=10)
        print(f'{name}: {r.status_code}')
        if r.status_code == 200:
            print(f'  → {r.text[:150]}')
    except Exception as e:
        print(f'{name}: ERROR - {e}')