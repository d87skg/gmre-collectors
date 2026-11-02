# -*- coding: utf-8 -*-
"""compare_shadow_run.py v3 - 兼容名字/编号/字段名差异"""
import json, csv, sys, re
from pathlib import Path
from datetime import datetime

BASE = Path(r"D:\HGZC")
SHADOW_DIR = BASE / "reports" / "stagflation_watch_2026Q3" / "shadow_run"
SHADOW_DIR.mkdir(parents=True, exist_ok=True)

THRESHOLDS = {"r_prob": 0.03, "fragility": 3.0, "shock": 0.10}

# S 状态名 → 编号
STRESS_NAME_TO_ID = {
    "RATES_STRESS": "S1",
    "STAGFLATION_STRESS": "S2",
    "CARRY_STRESS": "S3",
    "LIQUIDITY_BUFFER_DEPLETION": "S4",
    "FUNDING_STRESS": "S5",
    "CREDIT_STRESS": "S6",
    "CONTAGION": "S7",
    "SYSTEMIC_CRISIS": "S8",
}

# Shock 类型名（云端可能大小写不同）
SHOCK_TYPES = ["FISCAL", "LIQUIDITY", "POLICY", "SUPPLY",
               "FINANCIAL", "GEOPOLITICAL", "CREDIT"]

def load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def normalize_stress(s):
    """把名字/编号混合的列表统一成 S 编号"""
    if not s:
        return set()
    if isinstance(s, str):
        # 从字符串提取
        parts = re.split(r"[+,，、\s]+", s)
    else:
        parts = s
    out = set()
    for item in parts:
        item = str(item).strip()
        if not item:
            continue
        # 已经是 S 编号
        if re.match(r"^S[0-8]$", item):
            out.add(item)
            continue
        # 名字 → 编号
        upper = item.upper()
        for name, sid in STRESS_NAME_TO_ID.items():
            if name in upper:
                out.add(sid)
                break
    return out

def extract_stress(d):
    """兼容：stress=[S4,S5] / stress=[] + stress_overall='名字'"""
    s = d.get("stress", [])
    result = normalize_stress(s)
    if result:
        return result
    overall = d.get("stress_overall", "")
    return normalize_stress(overall)

def extract_shock(d):
    """兼容：
       本地: {"FISCAL": 0.757, "LIQUIDITY": 0.725}
       云端: {"primary": "FISCAL", "primary_intensity": 0.786,
              "secondary": "LIQUIDITY", "secondary_intensity": 0.725}
       或只有强度没名字：跳过（无法对账）
    """
    sh = d.get("shock", {})
    if not sh:
        return {}
    out = {}
    # 情况 1：{FISCAL: 0.757}
    for k, v in sh.items():
        if k.upper() in SHOCK_TYPES:
            try:
                out[k.upper()] = float(v)
            except (TypeError, ValueError):
                pass
    if out:
        return out
    # 情况 2：{primary: FISCAL, primary_intensity: X, ...}
    pn = sh.get("primary") or sh.get("primary_shock")
    pi = sh.get("primary_intensity")
    sn = sh.get("secondary") or sh.get("secondary_shock")
    si = sh.get("secondary_intensity")
    if pn and pi is not None:
        out[str(pn).upper()] = float(pi)
    if sn and si is not None:
        out[str(sn).upper()] = float(si)
    return out

def compare(local, shadow):
    diffs = []
    if not local or not shadow:
        return [{"field":"ALL","local":"N/A","shadow":"N/A","diff":"missing","level":"P0"}]

    # R 概率
    lr, sr = local.get("regime_probs", {}), shadow.get("regime_probs", {})
    for k in ["R0","R1","R2","R3","R4","R5","R6"]:
        lv, sv = lr.get(k,0), sr.get(k,0)
        d = abs(lv-sv)
        if d > THRESHOLDS["r_prob"]:
            diffs.append({"field":f"regime.{k}","local":f"{lv:.4f}","shadow":f"{sv:.4f}",
                          "diff":f"{d:.4f}","level":"P0" if d>0.05 else "P1"})

    # Fragility
    lf = local.get("fragility",{}).get("value",0)
    sf = shadow.get("fragility",{}).get("value",0)
    if abs(lf-sf) > THRESHOLDS["fragility"]:
        diffs.append({"field":"fragility.value","local":f"{lf:.1f}","shadow":f"{sf:.1f}",
                      "diff":f"{abs(lf-sf):.1f}","level":"P1"})

    # Stress（名字/编号兼容）
    ls, ss = extract_stress(local), extract_stress(shadow)
    if ls != ss:
        diffs.append({"field":"stress","local":",".join(sorted(ls)),
                      "shadow":",".join(sorted(ss)),
                      "diff":f"only_local={sorted(ls-ss)}, only_shadow={sorted(ss-ls)}",
                      "level":"P0"})

    # Shock
    lsh, ssh = extract_shock(local), extract_shock(shadow)
    for k in set(list(lsh)+list(ssh)):
        lv, sv = lsh.get(k,0), ssh.get(k,0)
        if abs(lv-sv) > THRESHOLDS["shock"]:
            diffs.append({"field":f"shock.{k}","local":f"{lv:.2f}","shadow":f"{sv:.2f}",
                          "diff":f"{abs(lv-sv):.2f}","level":"P1"})

    # Risk Gate
    lg, sg = local.get("risk_gate",""), shadow.get("risk_gate","")
    if lg != sg:
        diffs.append({"field":"risk_gate","local":lg,"shadow":sg,"diff":"mismatch","level":"P0"})

    # Defense
    ld, sd = local.get("defense_count",0), shadow.get("defense_count",0)
    if ld != sd:
        diffs.append({"field":"defense_count","local":str(ld),"shadow":str(sd),
                      "diff":str(abs(ld-sd)),"level":"P1"})
    return diffs

def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    local = load(SHADOW_DIR / f"local_{date}.json")
    shadow = load(SHADOW_DIR / f"shadow_{date}.json")
    diffs = compare(local, shadow)
    out_path = SHADOW_DIR / f"diff_{date}.csv"
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["field","local","shadow","diff","level"])
        w.writeheader()
        for d in diffs: w.writerow(d)
    print(f"[compare] date={date} diffs={len(diffs)}")
    for d in diffs:
        print(f"  [{d['level']}] {d['field']}: local={d['local']} shadow={d['shadow']} ({d['diff']})")
    print(f"[out] {out_path}")

if __name__ == "__main__":
    main()