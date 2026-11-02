# -*- coding: utf-8 -*-
"""tools/verify_feishu_vs_local.py - 飞书文本 vs 本地 macro.db 交叉验证
用法：先把飞书推送原文保存为 D:\\HGZC\\data\\latest_feishu.txt
"""
import re
import sqlite3
from pathlib import Path

DB_PATH = 'data/macro.db'
FEISHU_TXT = Path('data/latest_feishu.txt')


def parse_feishu(text):
    """从飞书文本提取关键指标"""
    d = {}

    # --- 机构与跨所验证 ---
    m = re.search(r'Coinbase溢价:\s*([+-]?\d+\.?\d*)%', text)
    d['coinbase_premium'] = float(m.group(1)) if m else None

    m = re.search(r'Bitget BTC FR:\s*([+-]?\d+\.?\d*)%', text)
    d['bitget_fr'] = float(m.group(1)) if m else None

    # --- HL 订单簿不平衡 ---
    m = re.search(r'BTC:\s*2%内买盘\s*[\d.]+\s*/\s*卖盘\s*[\d.]+\s*\|\s*不平衡\s*([+-]?\d+\.?\d*)', text)
    d['hl_imbalance_btc'] = float(m.group(1)) if m else None
    m = re.search(r'ETH:\s*2%内买盘\s*[\d.]+\s*/\s*卖盘\s*[\d.]+\s*\|\s*不平衡\s*([+-]?\d+\.?\d*)', text)
    d['hl_imbalance_eth'] = float(m.group(1)) if m else None

    # --- 稳定币总市值变化 ---
    m = re.search(r'稳定币总市值.*?\$([\d.]+)B', text, re.DOTALL)
    d['stablecoin_mcap'] = float(m.group(1)) if m else None
    m = re.search(r'1d:\s*([+-]?\d+\.?\d*)B', text)
    d['stablecoin_1d'] = float(m.group(1)) if m else None
    m = re.search(r'7d:\s*([+-]?\d+\.?\d*)B', text)
    d['stablecoin_7d'] = float(m.group(1)) if m else None

    # --- USDE 锚定偏离 ---
    m = re.search(r'USDE:.*?锚定\s*([+-]?\d+\.?\d*)%', text)
    d['usde_peg'] = float(m.group(1)) if m else None

    # --- OKX BTC FR ---
    m = re.search(r'OKX 永续 Funding.*?BTC:\s*([+-]?\d+\.?\d*)%', text, re.DOTALL)
    d['okx_btc_fr'] = float(m.group(1)) if m else None

    # --- Deribit DVOL ---
    m = re.search(r'Deribit DVOL.*?BTC:\s*([\d.]+)\s*\n\s*ETH:\s*([\d.]+)', text, re.DOTALL)
    if m:
        d['dvol_btc'] = float(m.group(1))
        d['dvol_eth'] = float(m.group(2))

    # --- 链上估值 ---
    m = re.search(r'MVRV:\s*([\d.]+)', text)
    d['mvrv'] = float(m.group(1)) if m else None
    m = re.search(r'SOPR:\s*([\d.]+)', text)
    d['sopr'] = float(m.group(1)) if m else None

    # --- Fear & Greed ---
    m = re.search(r'(\d+)\s*-\s*(Greed|Fear|Neutral)', text)
    if m:
        d['fear_greed'] = int(m.group(1))
        d['fear_greed_label'] = m.group(2)

    # --- 宏观相对定价 ---
    m = re.search(r'金铜比.*?:\s*([\d.]+)', text)
    d['gold_copper_ratio'] = float(m.group(1)) if m else None
    m = re.search(r'金油比.*?:\s*([\d.]+)', text)
    d['gold_oil_ratio'] = float(m.group(1)) if m else None

    # --- 市场指标 ---
    m = re.search(r'GOLD:\s*\$([\d,]+\.?\d*)', text)
    d['gold_price'] = float(m.group(1).replace(',', '')) if m else None
    m = re.search(r'OIL:\s*\$([\d,]+\.?\d*)', text)
    d['oil_price'] = float(m.group(1).replace(',', '')) if m else None
    m = re.search(r'DXY:\s*([\d.]+)', text)
    d['dxy'] = float(m.group(1)) if m else None
    m = re.search(r'USDJPY:\s*([\d.]+)', text)
    d['usdjpy'] = float(m.group(1)) if m else None
    m = re.search(r'VIX:\s*([\d.]+)', text)
    d['vix'] = float(m.group(1)) if m else None

    # --- FRED 宏观 ---
    m = re.search(r'HY OAS:\s*(\d+)bp', text)
    d['hy_oas_bp'] = int(m.group(1)) if m else None
    m = re.search(r'HY OAS 20D:\s*([+-]?\d+\.?\d*)%', text)
    d['hy_oas_20d_chg'] = float(m.group(1)) if m else None
    m = re.search(r'CCC:\s*(\d+)bp', text)
    d['hy_ccc_bp'] = int(m.group(1)) if m else None
    m = re.search(r'SOFR:\s*([\d.]+)%', text)
    d['sofr'] = float(m.group(1)) if m else None
    m = re.search(r'EFFR:\s*([\d.]+)%', text)
    d['effr'] = float(m.group(1)) if m else None
    m = re.search(r'ON RRP:\s*\$([\d.]+)B', text)
    d['rrp_b'] = float(m.group(1)) if m else None
    m = re.search(r'TGA:\s*\$([\d.]+)B', text)
    d['tga_b'] = float(m.group(1)) if m else None

    return d


def get_local_latest(conn, series_id):
    """从 observations 取最新值"""
    try:
        row = conn.execute(
            "SELECT timestamp, value FROM observations "
            "WHERE series_id=? ORDER BY timestamp DESC LIMIT 1",
            (series_id,)
        ).fetchone()
        return row if row else (None, None)
    except Exception:
        return (None, None)


def main():
    if not FEISHU_TXT.exists():
        print(f"❌ 文件不存在: {FEISHU_TXT}")
        print(f"   请先把飞书推送原文保存到: {FEISHU_TXT.absolute()}")
        return

    text = FEISHU_TXT.read_text(encoding='utf-8')
    feishu = parse_feishu(text)

    print(f"\n{'='*70}")
    print(f"  🔍 飞书 vs 本地 macro.db 交叉验证")
    print(f"{'='*70}\n")

    # 映射关系: 飞书字段 -> 本地 series_id（None 表示本地无对应）
    mapping = [
        ('GOLD 价格',           feishu.get('gold_price'),   'GOLD_PRICE',   'price'),
        ('OIL 价格',            feishu.get('oil_price'),    'WTI_OIL',      'price'),
        ('DXY',                 feishu.get('dxy'),          'DXY_PROXY',    'price'),
        ('USDJPY',              feishu.get('usdjpy'),       'USD_JPY',      'fx'),
        ('VIX',                 feishu.get('vix'),          'VIX',          'index'),
        ('HY OAS (bp)',         feishu.get('hy_oas_bp'),    'HY_SPREAD',    'spread_x100'),
        ('SOFR (%)',            feishu.get('sofr'),         'SOFR',         'rate'),
        ('EFFR (%)',            feishu.get('effr'),         'EFFR',         'rate'),
        ('ON RRP ($B)',         feishu.get('rrp_b'),        'RRP_BALANCE',  'rrp_scale'),
        ('TGA ($B)',            feishu.get('tga_b'),        'TGA_BALANCE',  'tga_scale'),
    ]

    conn = sqlite3.connect(DB_PATH)
    deviations = []

    for label, feishu_val, local_sid, kind in mapping:
        if feishu_val is None:
            print(f"  ⚠️  {label:20s} 飞书未解析到")
            continue

        local_date, local_val = get_local_latest(conn, local_sid)
        if local_val is None:
            print(f"  ❌ {label:20s} 飞书={feishu_val}  本地无 {local_sid}")
            continue

        # 单位换算
        if kind == 'spread_x100':
            local_val_cmp = float(local_val) * 100  # 3.29 -> 329
        elif kind == 'rrp_scale':
            local_val_cmp = float(local_val) / 1e9 if abs(float(local_val)) > 1e6 else float(local_val)
        elif kind == 'tga_scale':
            local_val_cmp = float(local_val) / 1e9 if abs(float(local_val)) > 1e6 else float(local_val)
        else:
            local_val_cmp = float(local_val)

        # 偏差
        if feishu_val != 0:
            pct_diff = abs(local_val_cmp - feishu_val) / abs(feishu_val) * 100
        else:
            pct_diff = 0

        # 状态标记
        if pct_diff < 1:
            flag = "✅"
        elif pct_diff < 5:
            flag = "🟡"
        else:
            flag = "🔴"
            deviations.append((label, feishu_val, local_val_cmp, pct_diff, local_date))

        print(f"  {flag} {label:20s} 飞书={feishu_val:>12.4f}  本地={local_val_cmp:>12.4f}  "
              f"偏差={pct_diff:5.2f}%  本地日期={local_date}")

    conn.close()

    # 飞书独有数据（本地没有的）
    print(f"\n{'='*70}")
    print(f"  📊 飞书独有数据（本地 macro.db 没有）")
    print(f"{'='*70}\n")

    feishu_only = [
        ('Coinbase 溢价',      feishu.get('coinbase_premium'),   '%'),
        ('Bitget BTC FR',      feishu.get('bitget_fr'),          '%'),
        ('OKX BTC FR',         feishu.get('okx_btc_fr'),         '%'),
        ('HL BTC 订单簿不平衡', feishu.get('hl_imbalance_btc'),   ''),
        ('HL ETH 订单簿不平衡', feishu.get('hl_imbalance_eth'),   ''),
        ('稳定币总市值',        feishu.get('stablecoin_mcap'),    '$B'),
        ('稳定币 1d 变化',      feishu.get('stablecoin_1d'),      '$B'),
        ('稳定币 7d 变化',      feishu.get('stablecoin_7d'),      '$B'),
        ('USDE 锚定偏离',       feishu.get('usde_peg'),           '%'),
        ('DVOL BTC',           feishu.get('dvol_btc'),           ''),
        ('DVOL ETH',           feishu.get('dvol_eth'),           ''),
        ('MVRV',               feishu.get('mvrv'),               ''),
        ('SOPR',               feishu.get('sopr'),               ''),
        ('Fear & Greed',       feishu.get('fear_greed'),         ''),
        ('金铜比',             feishu.get('gold_copper_ratio'),  ''),
        ('金油比',             feishu.get('gold_oil_ratio'),     ''),
        ('HY OAS 20D 变化',    feishu.get('hy_oas_20d_chg'),     '%'),
        ('CCC OAS (bp)',       feishu.get('hy_ccc_bp'),          'bp'),
    ]

    for label, val, unit in feishu_only:
        if val is not None:
            print(f"  ✓  {label:22s} {val}{unit}")
        else:
            print(f"  ⚠️  {label:22s} 未解析到")

    # 汇总
    print(f"\n{'='*70}")
    if deviations:
        print(f"  🔴 发现 {len(deviations)} 个显著偏差（>5%），需要排查:")
        for label, f_val, l_val, diff, l_date in deviations:
            print(f"     {label}: 飞书={f_val} vs 本地={l_val:.4f} (偏差 {diff:.1f}%, 本地日期 {l_date})")
    else:
        print(f"  ✅ 所有可比对指标偏差 < 5%，本地数据与飞书一致")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()