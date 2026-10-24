# -*- coding: utf-8 -*-
"""collectors/save_feishu_snapshot.py - 从飞书文本解析所有字段并写入 CSV"""
import csv
import os
import re
from datetime import datetime


def _num(s):
    """安全转 float，去掉千位分隔符"""
    if s is None:
        return ''
    try:
        return float(str(s).replace(',', ''))
    except Exception:
        return ''


def _int(s):
    try:
        return int(str(s).replace(',', ''))
    except Exception:
        return ''


def parse_and_save_snapshot(text):
    """从飞书文本解析所有字段，追加到 data/feishu_snapshot.csv"""
    d = {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

    # ========== 市场指标 ==========
    for sym in ['GOLD', 'OIL', 'COPPER', 'SILVER', 'WHEAT', 'NDX']:
        m = re.search(rf'{sym}:\s*\$?([\d,]+\.?\d*)', text)
        d[sym.lower()] = _num(m.group(1)) if m else ''
    m = re.search(r'DXY:\s*([\d.]+)', text)
    d['dxy'] = _num(m.group(1)) if m else ''
    m = re.search(r'USDJPY:\s*([\d.]+)', text)
    d['usdjpy'] = _num(m.group(1)) if m else ''
    m = re.search(r'VIX:\s*([\d.]+)', text)
    d['vix'] = _num(m.group(1)) if m else ''

    # ========== 宏观相对定价 ==========
    m = re.search(r'金铜比[^:]*:\s*([\d.]+)', text)
    d['gold_copper_ratio'] = _num(m.group(1)) if m else ''
    m = re.search(r'金美元比[^:]*:\s*([\d.]+)', text)
    d['gold_usd_ratio'] = _num(m.group(1)) if m else ''
    m = re.search(r'铜油比[^:]*:\s*([\d.]+)', text)
    d['copper_oil_ratio'] = _num(m.group(1)) if m else ''
    m = re.search(r'金油比[^:]*:\s*([\d.]+)', text)
    d['gold_oil_ratio'] = _num(m.group(1)) if m else ''
    m = re.search(r'金银比[^:]*:\s*([\d.]+)', text)
    d['gold_silver_ratio'] = _num(m.group(1)) if m else ''
    m = re.search(r'麦铜比[^:]*:\s*([\d.]+)', text)
    d['wheat_copper_ratio'] = _num(m.group(1)) if m else ''

    # ========== 国债收益率 ==========
    m = re.search(r'2Y:\s*([\d.]+)%', text)
    d['us_2y'] = _num(m.group(1)) if m else ''
    m = re.search(r'10Y:\s*([\d.]+)%', text)
    d['us_10y'] = _num(m.group(1)) if m else ''
    m = re.search(r'30Y:\s*([\d.]+)%', text)
    d['us_30y'] = _num(m.group(1)) if m else ''

    # ========== 信用 ==========
    m = re.search(r'HY OAS:\s*(\d+)bp', text)
    d['hy_oas_bp'] = _int(m.group(1)) if m else ''
    m = re.search(r'HY OAS 20D:\s*([+-]?\d+\.?\d*)%', text)
    d['hy_oas_20d_chg'] = _num(m.group(1)) if m else ''
    m = re.search(r'\n\s+BB:\s*(\d+)bp', text)
    d['hy_bb_bp'] = _int(m.group(1)) if m else ''
    m = re.search(r'\n\s+B:\s*(\d+)bp', text)  # 注意：\s+ 排除 BB 的 B
    d['hy_b_bp'] = _int(m.group(1)) if m else ''
    m = re.search(r'CCC:\s*(\d+)bp', text)
    d['hy_ccc_bp'] = _int(m.group(1)) if m else ''
    m = re.search(r'IG OAS:\s*(\d+)bp', text)
    d['ig_oas_bp'] = _int(m.group(1)) if m else ''
    m = re.search(r'AAA:\s*(\d+)bp', text)
    d['ig_aaa_bp'] = _int(m.group(1)) if m else ''
    m = re.search(r'BBB:\s*(\d+)bp', text)
    d['ig_bbb_bp'] = _int(m.group(1)) if m else ''

    # ========== 流动性 ==========
    m = re.search(r'SOFR:\s*([\d.]+)%', text)
    d['sofr'] = _num(m.group(1)) if m else ''
    m = re.search(r'EFFR:\s*([\d.]+)%', text)
    d['effr'] = _num(m.group(1)) if m else ''
    m = re.search(r'利差:\s*([+-]?\d+\.?\d*)bp', text)
    d['sofr_effr_spread_bp'] = _num(m.group(1)) if m else ''
    m = re.search(r'ON RRP:\s*\$([\d.]+)B', text)
    d['rrp_b'] = _num(m.group(1)) if m else ''
    m = re.search(r'TGA:\s*\$([\d.]+)B', text)
    d['tga_b'] = _num(m.group(1)) if m else ''
    m = re.search(r'准备金:\s*\$([\d.]+)T', text)
    d['reserve_t'] = _num(m.group(1)) if m else ''

    # ========== 机构与跨所 ==========
    m = re.search(r'Coinbase溢价:\s*([+-]?\d+\.?\d*)%', text)
    d['coinbase_premium'] = _num(m.group(1)) if m else ''
    m = re.search(r'Bitget BTC FR:\s*([+-]?\d+\.?\d*)%', text)
    d['bitget_btc_fr'] = _num(m.group(1)) if m else ''
    m = re.search(r'BTC FR 跨所差异\s*([\d.]+)%', text)
    d['fr_cross_diff'] = _num(m.group(1)) if m else ''

    # ========== Hyperliquid ==========
    m = re.search(r'BTC:\s*mid=\$?([\d,.]+)\s*\|\s*FR\s*([+-]?\d+\.?\d*)%\s*年化\s*\|\s*OI\s*\$([\d.]+)B', text)
    if m:
        d['hl_btc_mid'] = _num(m.group(1))
        d['hl_btc_fr'] = _num(m.group(2))
        d['hl_btc_oi_b'] = _num(m.group(3))
    else:
        d['hl_btc_mid'] = d['hl_btc_fr'] = d['hl_btc_oi_b'] = ''

    m = re.search(r'ETH:\s*mid=\$?([\d,.]+)\s*\|\s*FR\s*([+-]?\d+\.?\d*)%\s*年化\s*\|\s*OI\s*\$([\d.]+)B', text)
    if m:
        d['hl_eth_mid'] = _num(m.group(1))
        d['hl_eth_fr'] = _num(m.group(2))
        d['hl_eth_oi_b'] = _num(m.group(3))
    else:
        d['hl_eth_mid'] = d['hl_eth_fr'] = d['hl_eth_oi_b'] = ''

    m = re.search(r'BTC:\s*2%内买盘\s*[\d.]+\s*/\s*卖盘\s*[\d.]+\s*\|\s*不平衡\s*([+-]?\d+\.?\d*)', text)
    d['hl_imbalance_btc'] = _num(m.group(1)) if m else ''
    m = re.search(r'ETH:\s*2%内买盘\s*[\d.]+\s*/\s*卖盘\s*[\d.]+\s*\|\s*不平衡\s*([+-]?\d+\.?\d*)', text)
    d['hl_imbalance_eth'] = _num(m.group(1)) if m else ''

    # ========== 稳定币 ==========
    m = re.search(r'稳定币总市值.*?\$([\d.]+)B', text, re.DOTALL)
    d['stablecoin_mcap_b'] = _num(m.group(1)) if m else ''
    m = re.search(r'\n\s+1d:\s*([+-]?\d+\.?\d*)B', text)
    d['stablecoin_1d_b'] = _num(m.group(1)) if m else ''
    m = re.search(r'\n\s+7d:\s*([+-]?\d+\.?\d*)B', text)
    d['stablecoin_7d_b'] = _num(m.group(1)) if m else ''
    m = re.search(r'\n\s+30d:\s*([+-]?\d+\.?\d*)B', text)
    d['stablecoin_30d_b'] = _num(m.group(1)) if m else ''
    m = re.search(r'USDE:.*?锚定\s*([+-]?\d+\.?\d*)%', text)
    d['usde_peg'] = _num(m.group(1)) if m else ''
    m = re.search(r'FDUSD:.*?锚定\s*([+-]?\d+\.?\d*)%', text)
    d['fdusd_peg'] = _num(m.group(1)) if m else ''

    # ========== 期权 ==========
    m = re.search(r'Deribit DVOL.*?BTC:\s*([\d.]+)\s*\n\s*ETH:\s*([\d.]+)', text, re.DOTALL)
    if m:
        d['dvol_btc'] = _num(m.group(1))
        d['dvol_eth'] = _num(m.group(2))
    else:
        d['dvol_btc'] = d['dvol_eth'] = ''
    m = re.search(r'BTC RR25:\s*([+-]?\d+\.?\d*)%', text)
    d['btc_rr25'] = _num(m.group(1)) if m else ''
    m = re.search(r'ETH RR25:\s*([+-]?\d+\.?\d*)%', text)
    d['eth_rr25'] = _num(m.group(1)) if m else ''

    # ========== 链上 ==========
    m = re.search(r'MVRV:\s*([\d.]+)', text)
    d['mvrv'] = _num(m.group(1)) if m else ''
    m = re.search(r'SOPR:\s*([\d.]+)', text)
    d['sopr'] = _num(m.group(1)) if m else ''
    m = re.search(r'活跃地址:\s*([\d,]+)', text)
    d['btc_active_addr'] = _int(m.group(1)) if m else ''
    m = re.search(r'算力:\s*([\d.]+)\s*EH/s', text)
    d['btc_hashrate_eh'] = _num(m.group(1)) if m else ''

    # ========== 情绪 ==========
    m = re.search(r'(\d+)\s*-\s*(Greed|Fear|Neutral)', text)
    d['fear_greed'] = _int(m.group(1)) if m else ''
    m = re.search(r'BTC 市占率:\s*([\d.]+)%', text)
    d['btc_dominance'] = _num(m.group(1)) if m else ''
    m = re.search(r'ETH 市占率:\s*([\d.]+)%', text)
    d['eth_dominance'] = _num(m.group(1)) if m else ''
    m = re.search(r'TOTAL_MCAP:\s*\$([\d.]+)B', text)
    d['total_mcap_b'] = _num(m.group(1)) if m else ''

    # ========== ETF 净流 ==========
    m = re.search(r'BTC ETF 净流.*?(\d+ \w+ \d+):\s*US\$([+-]?[\d.]+)m', text, re.DOTALL)
    d['btc_etf_flow_usd_m'] = _num(m.group(2)) if m else ''
    m = re.search(r'5d 滚动:\s*US\$([+-]?[\d.]+)m', text)
    d['btc_etf_5d_usd_m'] = _num(m.group(1)) if m else ''
    m = re.search(r'ETH ETF 净流.*?US\$([+-]?[\d.]+)m', text, re.DOTALL)
    d['eth_etf_flow_usd_m'] = _num(m.group(1)) if m else ''

    # ========== 写入 CSV ==========
    csv_path = 'data/feishu_snapshot.csv'
    os.makedirs('data', exist_ok=True)
    file_exists = os.path.isfile(csv_path)

    fieldnames = list(d.keys())
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(d)

    non_empty = sum(1 for v in d.values() if v != '')
    print(f"✅ feishu_snapshot.csv 已更新: {csv_path}")
    print(f"   字段数: {len(d)}, 非空字段: {non_empty}")
    return d