import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from math import log, sqrt

def norm_cdf(x):
    return 0.5 * (1 + __import__('math').erf(x / sqrt(2)))

def calc_delta(S, K, T, sigma, is_call):
    if T <= 0 or sigma <= 0:
        return 0.5
    d1 = (log(S / K) + (0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    return norm_cdf(d1) if is_call else norm_cdf(d1) - 1

def get_options_summary(currency='BTC'):
    url = 'https://www.deribit.com/api/v2/public/get_book_summary_by_currency'
    params = {'currency': currency, 'kind': 'option'}
    res = requests.get(url, params=params, timeout=30)
    res.raise_for_status()
    return res.json().get('result', [])

def compute_signals(currency='BTC'):
    data = get_options_summary(currency)
    if not data: return None
    idx = requests.get('https://www.deribit.com/api/v2/public/get_index_price', params={'index_name': f'{currency.lower()}_usd'}, timeout=30).json()
    spot = float(idx['result']['index_price'])
    records = []
    for opt in data:
        name = opt.get('instrument_name', '')
        if '-' not in name: continue
        parts = name.split('-')
        if len(parts) < 4: continue
        expiry_str = parts[1]
        try:
            expiry = datetime.strptime(expiry_str, '%d%b%y').replace(tzinfo=timezone.utc)
        except: continue
        T = (expiry - datetime.now(timezone.utc)).total_seconds() / (365 * 86400)
        if T <= 0: continue
        K = float(parts[2])
        is_call = parts[3] == 'C'
        mark_iv = opt.get('mark_iv')
        if mark_iv is None: continue
        sigma = float(mark_iv) / 100.0
        delta = calc_delta(spot, K, T, sigma, is_call)
        records.append({'expiry': expiry_str, 'T': T, 'strike': K, 'is_call': is_call, 'delta': delta, 'iv': sigma, 'oi': float(opt.get('open_interest', 0) or 0)})
    df = pd.DataFrame(records)
    if df.empty: return None
    expiries = sorted(df['expiry'].unique(), key=lambda x: datetime.strptime(x, '%d%b%y'))
    chosen = [e for e in expiries if 7/365 < df[df['expiry'] == e]['T'].iloc[0] < 60/365]
    if not chosen: return None
    sub = df[df['expiry'] == chosen[0]].copy()
    calls, puts = sub[sub['is_call']], sub[~sub['is_call']]
    if calls.empty or puts.empty: return None
    call_25 = calls.iloc[(calls['delta'] - 0.25).abs().argsort()[:1]]
    put_25 = puts.iloc[(puts['delta'] + 0.25).abs().argsort()[:1]]
    rr25 = float(call_25['iv'].values[0]) - float(put_25['iv'].values[0])
    pcr = (puts['oi'].sum() / calls['oi'].sum()) if calls['oi'].sum() > 0 else None
    return {'currency': currency, 'spot': spot, 'rr25': rr25, 'pcr': pcr, 'expiry': chosen[0]}

def main():
    rows = []
    for c in ['BTC', 'ETH']:
        try:
            r = compute_signals(c)
            if r: rows.append(r)
        except Exception as e:
            print(f'{c} 失败: {e}')
    if rows:
        df = pd.DataFrame(rows)
        Path('data').mkdir(exist_ok=True)
        df.to_csv('data/deribit_skew.csv', index=False)
        print(f'✅ 已保存 {len(df)} 条期权信号至 data/deribit_skew.csv')

if __name__ == '__main__':
    main()