@echo off
cd /d D:\HGZC-collectors
echo [1] Financial Futures TFF
python -c "import requests; r=requests.get('https://publicreporting.cftc.gov/resource/gpe5-46if.json', params={'$limit': 1, '$order': 'report_date_as_yyyy_mm_dd DESC'}, timeout=30); print(r.status_code); print(r.text[:400])"

echo.
echo [2] Traders in Financial Futures - Futures Only
python -c "import requests; r=requests.get('https://publicreporting.cftc.gov/resource/gpe5-46if.json', params={'$limit': 1}, timeout=30); print(r.status_code)"

pause