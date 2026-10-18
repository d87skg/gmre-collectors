import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from math import log, sqrt, exp

def norm_cdf(x):
    # Abramowitz-Stegun 近似
    return 0.5 * (1 + __import__('math').erf(x / sqrt(2)))

def calc_delta(S, K, T, sigma, is_call):
    if T <= 0 or sigma <= 0:
        return 0.5
    d1 = (log(S / K) + (0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    if is_call:
        return norm_cdf(d1)
    else:
        return norm_cdf(d1) - 1

def get_options_summary(currency='BTC'):
    url = 'https://www.deribit.com/api/v2/public/get_book_summary_by_currency'
    params = {'currency': currency, 'kind': 'option'}
    res = requests.get(url, params=params, timeout=30)
    res.raise_for_status()
    return res.json().get('result', [])

def compute_signals(currency='BTC'):
    data = get_options_summary(currency)
    if not data:
        return None

    # 取现货指数价格（用 Deribit 的 index 端点）
    idx = requests.get('https://www.deribit.com/api/v2/public/get_index_price',
                       params={'index_name': f'{currency.lower()}_usd'}, timeout=30).json()
    spot = float(idx['result']['index_price'])

    records = []
    for opt in data:
        name = opt.get('instrument_name', '')
        if '-' not in name:
            continue
        parts = name.split('-')
        if len(parts) < 4:
            continue
        expiry_str = parts[1]
        try:
            expiry = datetime.strptime(expiry_str, '%d%b%y').replace(tzinfo=timezone.utc)
        except Exception:
            continue
        T = (expiry - datetime.now(timezone.utc)).total_seconds() / (365 * 86400)
        if T <= 0:
            continue
        K = float(parts[2])
        is_call = parts[3] == 'C'
        mark_iv = opt.get('mark_iv')
        if mark_iv is None:
            continue
        sigma = float(mark_iv) / 100.0
        delta = calc_delta(spot, K, T, sigma, is_call)
        records.append({
            'expiry': expiry_str,
            'T': T,
            'strike': K,
            'is_call': is_call,
            'delta': delta,
            'iv': sigma,
            'oi': float(opt.get('open_interest', 0) or 0),
            'volume': float(opt.get('volume', 0) or 0),
            'underlying_price': spot,
        })

    df = pd.DataFrame(records)
    if df.empty:
        return None

    # 选最近到期的有流动性的期权（>7天，<60天）
    expiries = sorted(df['expiry'].unique(), key=lambda x: datetime.strptime(x, '%d%b%y'))
    chosen = [e for e in expiries if 7/365 < df[df['expiry'] == e]['T'].iloc[0] < 60/365]
    if not chosen:
        chosen = [expiries[0]] if expiries else []
    if not chosen:
        return None
    target_exp = chosen[0]
    sub = df[df['expiry'] == target_exp].copy()

    # 找 25-delta 的 call 和 put（取 delta 最接近 ±0.25 的）
    calls = sub[sub['is_call']].copy()
    puts = sub[~sub['is_call']].copy()

    if calls.empty or puts.empty:
        return None

    call_25 = calls.iloc[(calls['delta'] - 0.25).abs().argsort()[:1]]
    put_25 = puts.iloc[(puts['delta'] + 0.25).abs().argsort()[:1]]

    if call_25.empty or put_25.empty:
        return None

    rr25 = float(call_25['iv'].values[0]) - float(put_25['iv'].values[0])

    put_notional = (puts['oi'] * puts['strike']).sum()
    call_notional = (calls['oi'] * calls['strike']).sum()
    pcr = (put_notional / call_notional) if call_notional > 0 else None

    # 期限结构：近月 ATM IV / 远月 ATM IV
    front_atm = sub.iloc[(sub['delta'] - 0.5).abs().argsort()[:1]]['iv'].values
    far_candidates = df[df['T'] > sub['T'].max() * 1.5]
    far_atm = None
    if not far_candidates.empty:
        far_exp = sorted(far_candidates['expiry'].unique(), key=lambda x: datetime.strptime(x, '%d%b%y'))[0]
        far_sub = far_candidates[far_candidates['expiry'] == far_exp]
        far_atm = far_sub.iloc[(far_sub['delta'] - 0.5).abs().argsort()[:1]]['iv'].values

    term_ratio = float(front_atm[0]) / float(far_atm[0]) if (front_atm.size and far_atm is not None and far_atm.size) else None

    return {
        'currency': currency,
        'spot': spot,
        'rr25': rr25,
        'pcr': pcr,
        'term_ratio': term_ratio,
        'expiry': target_exp,
        'as_of': datetime.now(timezone.utc).isoformat(),
    }

def main():
    rows = []
    for c in ['BTC', 'ETH']:
        try:
            r = compute_signals(c)
            if r:
                rows.append(r)
                print(f'{c} RR25={r["rr25"]:.3f}, PCR={r["pcr"]:.3f}, Term={r["term_ratio"]}')
        except Exception as e:
            print(f'{c} 失败: {e}')

    if rows:
        df = pd.DataFrame(rows)
        Path('data').mkdir(exist_ok=True)
        df.to_csv('data/deribit_skew.csv', index=False)
        print(f'✅ 已保存 {len(df)} 条期权信号')
    else:
        print('❌ 未获取到信号')

if __name__ == '__main__':
    main()