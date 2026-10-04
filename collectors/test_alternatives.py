"""
测试 Binance（curl_cffi）+ CME API 在 Actions 环境是否可达
"""
from curl_cffi import requests as cffi_requests
import requests

print("===== Binance fapi (curl_cffi) =====")
try:
    r = cffi_requests.get(
        'https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT',
        impersonate='chrome', timeout=15
    )
    print(f'  premiumIndex: {r.status_code} | {r.text[:150]}')
except Exception as e:
    print(f'  premiumIndex 失败: {e}')

try:
    r = cffi_requests.get(
        'https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1h&limit=5',
        impersonate='chrome', timeout=15
    )
    print(f'  openInterestHist: {r.status_code} | {r.text[:150]}')
except Exception as e:
    print(f'  openInterestHist 失败: {e}')

try:
    r = cffi_requests.get(
        'https://fapi1.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT',
        impersonate='chrome', timeout=15
    )
    print(f'  fapi1 premiumIndex: {r.status_code} | {r.text[:150]}')
except Exception as e:
    print(f'  fapi1 失败: {e}')

print("\n===== CME API =====")
try:
    r = requests.get(
        'https://www.cmegroup.com/CmeWS/mvc/ProductCalendar/Future/305/FUT',
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
        timeout=15
    )
    print(f'  ProductCalendar: {r.status_code} | {r.text[:200]}')
except Exception as e:
    print(f'  ProductCalendar 失败: {e}')

try:
    r = requests.get(
        'https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/305/FUT',
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
        timeout=15
    )
    print(f'  Settlements: {r.status_code} | {r.text[:200]}')
except Exception as e:
    print(f'  Settlements 失败: {e}')