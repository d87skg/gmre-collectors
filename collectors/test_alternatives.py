"""
测试 Binance（curl_cffi）+ CME API 在 Actions 环境是否可达
"""
from curl_cffi import requests as cffi_requests
import requests
import sys

def log(msg):
    print(msg, flush=True)

log("========== TEST ALTERNATIVES ==========")

log("[1] Binance fapi premiumIndex (curl_cffi)")
try:
    r = cffi_requests.get(
        'https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT',
        impersonate='chrome', timeout=15
    )
    log(f'    status: {r.status_code}')
    log(f'    body: {r.text[:200]}')
except Exception as e:
    log(f'    EXC: {type(e).__name__}: {e}')

log("[2] Binance openInterestHist (curl_cffi)")
try:
    r = cffi_requests.get(
        'https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1h&limit=5',
        impersonate='chrome', timeout=15
    )
    log(f'    status: {r.status_code}')
    log(f'    body: {r.text[:200]}')
except Exception as e:
    log(f'    EXC: {type(e).__name__}: {e}')

log("[3] Binance fapi1 premiumIndex (curl_cffi)")
try:
    r = cffi_requests.get(
        'https://fapi1.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT',
        impersonate='chrome', timeout=15
    )
    log(f'    status: {r.status_code}')
    log(f'    body: {r.text[:200]}')
except Exception as e:
    log(f'    EXC: {type(e).__name__}: {e}')

log("[4] CME ProductCalendar")
try:
    r = requests.get(
        'https://www.cmegroup.com/CmeWS/mvc/ProductCalendar/Future/305/FUT',
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
        timeout=15
    )
    log(f'    status: {r.status_code}')
    log(f'    body: {r.text[:200]}')
except Exception as e:
    log(f'    EXC: {type(e).__name__}: {e}')

log("[5] CME Settlements")
try:
    r = requests.get(
        'https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/305/FUT',
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
        timeout=15
    )
    log(f'    status: {r.status_code}')
    log(f'    body: {r.text[:200]}')
except Exception as e:
    log(f'    EXC: {type(e).__name__}: {e}')

log("========== END TEST ==========")