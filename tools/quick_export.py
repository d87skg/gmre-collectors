"""tools/quick_export.py - 最小化导出（修复缩进版）"""
import sqlite3
import json
from datetime import datetime

DB = 'D:/HGZC/data/macro.db'
asof = datetime.now().strftime('%Y-%m-%d')

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=" * 70)
print("  GMRE 3.3 快速快照 - " + asof)
print("=" * 70)
print()

# 【1】关键原始数据
print("【1】关键原始数据")
print("-" * 70)
for sid in ['YC10Y','YC2Y','YC30Y','FEDFUNDS','USD_JPY','RRP_BALANCE',
            'TGA_BALANCE','FED_WALCL','RESERVE_BALANCE','SOFR','EFFR',
            'HY_SPREAD','VIX','WTI_OIL','BRENT_OIL','SP500','DXY_PROXY',
            'CPIAUCSL','MICH_1Y_EXPECT','JOBLESS_CLAIMS','UNEMPLOYMENT']:
    row = c.execute(
        "SELECT timestamp, value, source FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1",
        (sid,)
    ).fetchone()
    if row:
        val = row['value'] if row['value'] is not None else 0.0
        ts = str(row['timestamp']) if row['timestamp'] else 'N/A'
        src = str(row['source']) if row['source'] else 'N/A'
        print(sid + "  |  " + str(round(val, 4)) + "  |  " + ts + "  |  " + src)
    else:
        print(sid + "  |  N/A  |  N/A  |  N/A")

# 【2】5引擎 Z-score
print()
print("【2】5引擎 Z-score")
print("-" * 70)
rows = c.execute("""
    SELECT engine_id, z_score, direction
    FROM engine_latents
    WHERE asof_date = (SELECT MAX(asof_date) FROM engine_latents)
""").fetchall()
for r in rows:
    print(r['engine_id'] + "  |  Z=" + str(round(r['z_score'], 4)) + "  |  " + str(r['direction']))

# 【3】GMS Regime
print()
print("【3】GMS Regime")
print("-" * 70)
r = c.execute("SELECT * FROM gms_regimes ORDER BY asof_date DESC LIMIT 1").fetchone()
if r:
    for k in r.keys():
        print("  " + k + ": " + str(r[k]))

# 【4】Stress Overlay V2
print()
print("【4】Stress Overlay V2")
print("-" * 70)
r = c.execute("SELECT * FROM stress_overlay_v2 ORDER BY asof_date DESC LIMIT 1").fetchone()
if r:
    print("  overall: " + str(r['overall']))
    print("  triggered_count: " + str(r['triggered_count']))
    print("  systemic_confirmed: " + str(r['systemic_confirmed']))

# 【5】Fragility
print()
print("【5】Fragility Engine")
print("-" * 70)
r = c.execute("SELECT * FROM fragility_engine ORDER BY asof_date DESC LIMIT 1").fetchone()
if r:
    print("  level: " + str(r['level']))
    print("  score: " + str(r['fragility_score']))
    print("  base: " + str(r['base_fragility']))
    print("  amplification: " + str(r['amplification']))
    try:
        detail = json.loads(r['detail'])
        print("  维度:")
        for name, d in detail.items():
            if isinstance(d, dict):
                print("    " + name + " = " + str(round(d.get('score', 0), 1)))
    except Exception:
        pass

# 【6】Shock
print()
print("【6】Shock Engine")
print("-" * 70)
r = c.execute("SELECT * FROM shock_engine ORDER BY asof_date DESC LIMIT 1").fetchone()
if r:
    print("  primary: " + str(r['primary_shock']) + " (I=" + str(r['primary_intensity']) + ")")
    print("  secondary: " + str(r['secondary_shock']))

# 【7】Transmission
print()
print("【7】Transmission Graph")
print("-" * 70)
r = c.execute("SELECT detail FROM transmission_graph ORDER BY asof_date DESC LIMIT 1").fetchone()
if r:
    try:
        chains = json.loads(r['detail'])
        for chain in chains:
            print("  " + chain.get('name', '')[:50])
            print("    状态: " + str(chain.get('status')) + " | 激活度: " + str(round(chain.get('activation', 0), 3)))
    except Exception as e:
        print("  解析失败: " + str(e))

# 【8】Probability
print()
print("【8】Probability")
print("-" * 70)
r = c.execute("SELECT * FROM probability_engine ORDER BY asof_date DESC LIMIT 1").fetchone()
if r:
    print("  P(R0-R5): " + str(r['p_r0']) + ", " + str(r['p_r1']) + ", " + str(r['p_r2']) + ", " + str(r['p_r3']) + ", " + str(r['p_r4']) + ", " + str(r['p_r5']))
    print("  P(R4+R5): " + str(r['high_risk_prob']))

# 【9】Defense
print()
print("【9】Defense V4")
print("-" * 70)
r = c.execute("SELECT * FROM defense_v4 ORDER BY asof_date DESC LIMIT 1").fetchone()
if r:
    print("  triggered: " + str(r['triggered_count']) + "/7")
    print("  systemic: " + str(r['systemic_confirmed']))

# 【10】Crisis Fingerprint
print()
print("【10】Crisis Fingerprint")
print("-" * 70)
r = c.execute("SELECT detail FROM crisis_fingerprint ORDER BY asof_date DESC LIMIT 1").fetchone()
if r:
    try:
        fps = json.loads(r['detail'])
        for fp in fps[:5]:
            print("  " + str(fp.get('crisis', '')) + "  |  " + str(round(fp.get('similarity', 0), 3)))
    except Exception:
        pass

print()
print("=" * 70)
conn.close()