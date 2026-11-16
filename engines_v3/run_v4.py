"""engines_v3/run_v4.py - GMRE 4.1 完整集成版（v5.6: Probability 源码内证 + BLACK 兼容）"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import io, contextlib, sqlite3, subprocess, hashlib, json, math, pandas as pd
from datetime import datetime

from engines_v2 import (
    engine_liq, engine_inf, engine_mon, engine_risk, engine_fis,
    regime_map, yen_carry_state, liquidity_alert, hedge_advisor,
    data_quality_check, dau_alert
)
from engines_v3 import (
    stress_overlay_v2, defense_v4, engine_mon_v2, engine_fis_v2,
    engine_inf_expect, invalidation_conditions
)
from engines_v3.event_scenario_engine import evaluate_event_scenario, TradePerm
from core.data_proxy import load, peek

try:
    from tools.check_events import check_upcoming_events
except ImportError:
    check_upcoming_events = lambda **kwargs: []

try:
    from tools.rrp_guard import run_rrp_guard
except ImportError:
    run_rrp_guard = None

from core.errors import preflight, print_preflight, DataError, handle

DB_PATH = os.environ.get('GMRE_DB_PATH', 'data/macro.db')

_DATA_ELIGIBILITY = {}
_DATA_STALENESS = {}
_DATA_HEALTH = {}


def get_git_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=3, check=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        commit = result.stdout.strip()
        return commit[:8] if commit else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def get_series_meta(sid, override_value=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            try:
                series = load(conn, sid, limit=1)
                if not series.empty:
                    date_str = pd.to_datetime(series.index[-1]).strftime('%Y-%m-%d')
                    raw_val = float(series.iloc[-1])
                    value = override_value if override_value is not None else raw_val
                    lag = (datetime.now() - pd.to_datetime(date_str)).days
                    return date_str, value, lag
            except DataError:
                pass
        finally:
            conn.close()
    except Exception:
        pass
    if override_value is not None:
        return datetime.now().strftime('%Y-%m-%d'), override_value, 0
    return "N/A", None, 999


def get_series_meta_full(sid, override_value=None):
    used_id = sid
    proxy_used = False
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            try:
                info = peek(conn, sid)
                if info:
                    used_id = info.get('series_used', sid)
                    proxy_used = (used_id != sid)
            except Exception:
                pass
            date_str, value, lag = get_series_meta(sid, override_value=override_value)
            return date_str, value, lag, used_id, proxy_used
        finally:
            conn.close()
    except Exception:
        date_str, value, lag = get_series_meta(sid, override_value=override_value)
        return date_str, value, lag, used_id, proxy_used


def check_eligibility(sid, max_lag):
    _, v, lag = get_series_meta(sid)
    _DATA_STALENESS[sid] = lag
    if v is None:
        _DATA_ELIGIBILITY[sid] = (False, "MISSING")
    elif lag > max_lag:
        _DATA_ELIGIBILITY[sid] = (False, f"STALE (lag={lag}d > {max_lag}d)")
    else:
        _DATA_ELIGIBILITY[sid] = (True, "OK")


def is_eligible(sid):
    eligible, _ = _DATA_ELIGIBILITY.get(sid, (False, "UNKNOWN"))
    return eligible


def compute_risk_gate(frag_level, stress_overall, contagion_status,
                      systemic_confirmed, p_r4_r5=None, missing_engines=None,
                      prob_decision_eligible=True):
    if p_r4_r5 is None:
        return 'UNKNOWN', '🚨 P(R4+R5) 概率未知 (计算故障)'
    if frag_level == 'N/A' or frag_level is None:
        return 'UNKNOWN', '🚨 数据缺失'
    try:
        frag_score = float(frag_level.split('(')[1].split(')')[0])
        if not math.isfinite(frag_score):
            return 'UNKNOWN', '🚨 数值异常'
    except Exception:
        return 'SAFE_MODE', '🚨 计算故障'
    if systemic_confirmed:
        return 'BLACK', '🚨 系统性危机已确认'

    red_reasons = []
    if frag_score >= 80:
        red_reasons.append(f"Fragility={frag_score:.1f}≥80")
    if 'FUNDING_STRESS' in stress_overall and 'CREDIT_STRESS' in stress_overall:
        red_reasons.append("FUNDING+CREDIT_STRESS 共振")
    if p_r4_r5 >= 0.50:
        red_reasons.append(f"P(R4+R5)={p_r4_r5*100:.1f}%≥50%")
    if missing_engines:
        red_reasons.append(f"核心引擎缺失: {missing_engines}")
    if not prob_decision_eligible:
        red_reasons.append("PROBABILITY_INELIGIBLE")
    if red_reasons:
        return 'RED', f'🔴 高风险：{", ".join(red_reasons)}'

    orange_reasons = []
    if frag_score >= 65:
        orange_reasons.append(f"Fragility={frag_score:.1f}≥65")
    if stress_overall.count('+') >= 1:
        orange_reasons.append(f"Stress={stress_overall}")
    if p_r4_r5 >= 0.30:
        orange_reasons.append(f"P(R4+R5)={p_r4_r5*100:.1f}%≥30%")
    if orange_reasons:
        return 'ORANGE', f'🟠 中高风险：{", ".join(orange_reasons)}'

    if frag_score >= 50:
        return 'YELLOW', f'🟡 中等：Fragility={frag_score:.1f}'
    return 'GREEN', f'🟢 低风险：Fragility={frag_score:.1f}'


def get_dual_phase_guide(gate, frag_score, cali_score, scenario, dxy_pct):
    if cali_score and cali_score >= 60:
        phase, emoji = '上半场（去杠杆中）', '🔴'
    elif dxy_pct is not None and dxy_pct < 10:
        phase, emoji = '上半场尾部（流动性枯竭末期）', '🟠'
    elif gate in ('ORANGE', 'YELLOW'):
        phase, emoji = '过渡期（政策底已现，市场底待确认）', '🟡'
    elif dxy_pct is None:
        phase, emoji = '过渡期（数据缺失，默认防守）', '🟡'
    else:
        phase, emoji = '下半场（降息重估）', '🟢'
    if phase.startswith('上半场'):
        cash, gold, note = '50-70%', '5-10%', '现金为王，等右侧信号'
    elif phase.startswith('过渡'):
        cash, gold, note = '40-60%', '7-10%', '保持防守，分批左侧埋伏'
    else:
        cash, gold, note = '10-20%', '5-10%', '子弹打出去，享受估值重估'
    return {'phase': phase, 'phase_emoji': emoji,
            'cash_recommendation': cash, 'gold_recommendation': gold, 'note': note}


def _probe(series_id):
    """
    数据体检探针：支持 series 别名链，**在所有候选中选择最新的那个**。
    与 core.data_proxy._resolve 逻辑一致。
    """
    from core import units

    candidates = [series_id]
    try:
        for cand in units.candidates_of(series_id):
            if cand not in candidates:
                candidates.append(cand)
    except Exception:
        pass

    results = []
    for cand in candidates:
        for tbl, col in (('observations_v2', 'obs_date'), ('observations', 'timestamp')):
            try:
                conn = sqlite3.connect(DB_PATH)
                row = conn.execute(
                    f"SELECT MAX({col}) FROM {tbl} WHERE series_id=?", (cand,)
                ).fetchone()
                conn.close()
                if row and row[0]:
                    results.append((cand, str(row[0])[:10]))
                    break
            except sqlite3.OperationalError:
                continue

    if not results:
        return None

    # 按日期最新排序，返回最新的
    results.sort(key=lambda x: x[1], reverse=True)
    return {'obs_date': results[0][1], 'series_used': results[0][0]}


def data_preflight(asof=None):
    report = preflight(_probe, asof=asof)
    print_preflight(report)
    _DATA_HEALTH['preflight'] = {
        'verdict': report['verdict'],
        'block': len(report['block']),
        'degrade': len(report['degrade'])
    }
    if report['verdict'] == 'BLOCK':
        first = report['block'][0]
        from core.errors import DataStaleError
        raise DataStaleError(first['series_id'], first['days_lag'], first['sla_days'], obs_date=first['obs_date'])


def main():
    asof = datetime.now().strftime('%Y-%m-%d')
    print(f"\n{'='*60}\n  GMRE 4.1 完整版 - {asof}\n{'='*60}\n")

    event_perm_name, event_perm_reason = "UNKNOWN", "NOT_RUN"
    shadow_weights = {}
    archive_status = "NOT_STARTED"
    archive_error = None
    p_r4_r5_val = None
    prob_input_audit = {}
    mon_v2_comp = None
    fis_v2_comp = None
    micro_res = {}

    check_eligibility('MICH_1Y_EXPECT', 45)
    check_eligibility('FEDFUNDS', 45)
    check_eligibility('HY_OAS', 3)
    check_eligibility('YC10Y', 3)
    check_eligibility('SP500', 3)
    check_eligibility('VIX', 3)

    data_preflight(asof=asof)

    print(f"{'-'*50}\n  📅 宏观事件倒计时检查\n{'-'*50}")
    check_upcoming_events(config_path="config/events_calendar.yaml")
    print(f"{'-'*50}\n")

    audit_status_raw = 'UNKNOWN'
    regime_label = 'UNKNOWN'
    frag_score_val = 0.0

    print(f"{'-'*60}")
    try:
        audit = data_quality_check.run_audit(asof)
        audit_status_raw = audit['status']
        icon = {'PASS': '✅', 'WARN': '⚠️', 'FAIL': '❌'}.get(audit['status'], '?')
        print(f"  {icon} 数据自检(原始): {audit['status']} (通过{audit['pass_count']}/警告{audit['warn_count']}/严重{audit['critical_count']})")
    except Exception as e:
        print(f"  ⚠️ 数据自检异常: {e}")

    try:
        hy_date, hy_val, hy_lag, hy_used, hy_proxy = get_series_meta_full('HY_OAS')
        hy_raw_eligible = is_eligible('HY_OAS')
        print("\n  [HY_OAS 代理状态]")
        print(f"    HY_OAS_RAW         : {'OK' if hy_raw_eligible else 'MISSING'}")
        print(f"    HY_SPREAD          : {'OK' if hy_val is not None else 'MISSING'}")
        print(f"    HY_OAS_EFFECTIVE   : {hy_val if hy_val is not None else 'N/A'}")
        print(f"    USED_SERIES        : {hy_used}")
        print(f"    PROXY_USED         : {hy_proxy}")
        print(f"    DECISION_ELIGIBLE  : {hy_val is not None and hy_lag <= 3}")
    except Exception as e:
        print(f"  ⚠️ HY_OAS 代理状态输出失败: {e}")

    print(f"\n┌{'─'*58}┐\n│  【轨道1】Base Regime (R0-R6)                     │\n└{'─'*58}┘\n")

    fed_eligible, fed_reason = _DATA_ELIGIBILITY.get('FEDFUNDS', (False, 'UNKNOWN'))
    missing_engines = []
    engine_z_values = {}

    for mod in [engine_inf, engine_mon, engine_fis, engine_liq, engine_risk]:
        try:
            if mod.ENGINE_ID == 'MON' and not fed_eligible:
                print(f"  [MON] ⛔ FEDFUNDS {fed_reason}，Base MON 强制跳过。")
                missing_engines.append('MON')
                continue
            r = mod.compute_engine(asof)
            engine_z_values[r['engine_id']] = r['z_score']
            print(f"  [{r['engine_id']}] Z={r['z_score']:+.4f} | {r['direction']}")
        except Exception as e:
            print(f"  [{mod.ENGINE_ID}] ❌ 失败: {e}")
            missing_engines.append(mod.ENGINE_ID)

    try:
        if not fed_eligible:
            print(f"  [MON_V2] ⛔ FEDFUNDS {fed_reason}，MON V2 强制跳过。")
            if 'MON_V2' not in missing_engines:
                missing_engines.append('MON_V2')
        else:
            mon_v2 = engine_mon_v2.compute_mon_v2(asof)
            mon_v2_comp = mon_v2.get('composite', 0)
            if math.isnan(mon_v2_comp):
                print("  [MON_V2] 🚨 数据异常 (NaN)，已冻结拒绝输出！")
                mon_v2_comp = None
            else:
                print(f"  [MON_V2] Composite={mon_v2_comp:+.4f} | {mon_v2['direction']}")
    except Exception as e:
        print(f"  [MON_V2] ❌ 计算失败: {e}")

    try:
        fis_v2 = engine_fis_v2.compute_fis_v2(asof)
        fis_v2_comp = fis_v2.get('composite', 0)
        if math.isnan(fis_v2_comp):
            print("  [FIS_V2] 🚨 数据异常 (NaN)，已冻结拒绝输出！")
            fis_v2_comp = None
        else:
            print(f"  [FIS_V2] Composite={fis_v2_comp:+.4f} | {fis_v2['direction']}")
    except Exception as e:
        print(f"  [FIS_V2] ❌ 计算失败: {e}")

    try:
        mich_eligible, mich_reason = _DATA_ELIGIBILITY.get('MICH_1Y_EXPECT', (False, 'UNKNOWN'))
        if not mich_eligible:
            print(f"  [INF_EXPECT] ⛔ MICH_1Y {mich_reason}，强制禁用。")
            if 'INF_EXPECT' not in missing_engines:
                missing_engines.append('INF_EXPECT')
        else:
            inf_exp = engine_inf_expect.compute_engine(asof)
            if inf_exp.get('level') != 'MISSING_DATA':
                print(f"  [INF_EXPECT] Stress={inf_exp['inf_expect_stress']}/100 | {inf_exp['level']}")
    except Exception:
        pass

    print(f"\n{'-'*60}")
    regime = {}
    try:
        regime = regime_map.run(asof)
        if regime:
            regime_label = regime['regime_label']
            print(f"  GMS体制: {regime['regime_label']} ({regime['regime_name']})")
            raw_conf = regime.get('raw_confidence', regime.get('confidence', 0))
            adj_conf = regime.get('confidence', 0)
            if regime.get('raw_confidence') is not None and raw_conf != adj_conf:
                print(f"  置信度: {adj_conf*100:.1f}% (原始 {raw_conf*100:.1f}%，已折扣)")
            else:
                print(f"  置信度: {adj_conf*100:.1f}%")
    except Exception as e:
        print(f"  ⚠️ GMS异常: {e}")

    print("\n  [ENGINE_FUSION_AUDIT]")
    print(f"    MON_BASE_Z              : {engine_z_values.get('MON', 'N/A')}")
    print(f"    MON_V2_COMPOSITE        : {mon_v2_comp if mon_v2_comp is not None else 'N/A'}")
    print(f"    MON_GMS_INPUT           : Z (engine_latents)")
    print(f"    MON_FUSION_METHOD       : GMS 使用 Base Z，V2 仅作辅助展示")
    print(f"    FIS_BASE_Z              : {engine_z_values.get('FIS', 'N/A')}")
    print(f"    FIS_V2_COMPOSITE        : {fis_v2_comp if fis_v2_comp is not None else 'N/A'}")
    print(f"    FIS_GMS_INPUT           : Z (engine_latents)")
    print(f"    FIS_FUSION_METHOD       : GMS 使用 Base Z，V2 仅作辅助展示")

    print("\n  [ENGINE_DIVERGENCE_AUDIT]")
    mon_base = engine_z_values.get('MON')
    fis_base = engine_z_values.get('FIS')
    mon_diff = (mon_v2_comp - mon_base) if (mon_v2_comp is not None and mon_base is not None) else None
    fis_diff = (fis_v2_comp - fis_base) if (fis_v2_comp is not None and fis_base is not None) else None
    print(f"    MON_Z_VS_V2_DIFF        : {mon_diff:+.4f}" if mon_diff is not None else "    MON_Z_VS_V2_DIFF        : N/A")
    print(f"    FIS_Z_VS_V2_DIFF        : {fis_diff:+.4f}" if fis_diff is not None else "    FIS_Z_VS_V2_DIFF        : N/A")
    print(f"    DIVERGENCE_PERSISTENCE  : N/A (需历史回放)")
    print(f"    V2_SHADOW_BACKTEST_STATUS : NOT_STARTED")
    print(f"    V2_PRODUCTION_ELIGIBLE  : FALSE (审计建议：先做影子信号积累)")

    gms_health = regime.get('health', {}) if regime else {}
    if gms_health:
        print("\n  [GMS_INPUT_HEALTH]")
        print(f"    valid_engines              : {gms_health.get('valid_engines', 'N/A')}")
        print(f"    missing_engines            : {gms_health.get('missing_engines', 'N/A')}")
        print(f"    GMS_WEIGHT_RENORMALIZED    : {gms_health.get('weight_renormalized', 'N/A')}")
        print(f"    GMS_CONFIDENCE_ADJUSTED    : {gms_health.get('confidence_adjusted', 'N/A')}")
        print(f"    GMS_CONFIDENCE_DISCOUNT    : {gms_health.get('confidence_discount', 'N/A')}")
        print(f"    GMS_DEGRADED               : {gms_health.get('degraded', 'N/A')}")
        print(f"    GMS_REASON                 : {gms_health.get('reason', 'N/A')}")
    else:
        valid_engines = 5 - len([m for m in missing_engines if m in ('INF', 'MON', 'FIS', 'LIQ', 'RISK')])
        print("\n  [GMS_INPUT_HEALTH] (regime 未返回 health 字段，使用本地计数)")
        print(f"    valid_engines              : {max(valid_engines, 0)}")
        print(f"    missing_engines            : {missing_engines if missing_engines else 'NONE'}")
        print(f"    GMS_WEIGHT_RENORMALIZED    : UNVERIFIED")
        print(f"    GMS_CONFIDENCE_ADJUSTED    : UNVERIFIED")
        print(f"    GMS_DEGRADED               : {bool(missing_engines)}")

    print(f"\n┌{'─'*58}┐\n│  【预轨】Fragility（提前计算）                       │\n└{'─'*58}┘\n")
    frag_level = 'N/A'
    try:
        from engines_v3 import fragility_engine
        with contextlib.redirect_stdout(io.StringIO()):
            _frag_pre = fragility_engine.compute_fragility(asof)
        frag_level = f"{_frag_pre['level']} ({_frag_pre['fragility_score']})"
        frag_score_val = _frag_pre['fragility_score']
        print(f"  [Fragility] {frag_level}")
    except Exception as e:
        print(f"  ⚠️ Fragility 提前计算失败: {e}")

    print(f"\n{'─'*50}\n  🔍 核心数据溯源（日频决策口径唯一）")
    rrp_override, rrp_source_tag = None, ""
    if run_rrp_guard is not None:
        try:
            _g = run_rrp_guard(verbose=False)
            if _g.primary_value is not None:
                rrp_override = float(_g.primary_value)
                rrp_source_tag = f" [{_g.primary_source}]"
        except Exception:
            pass

    audit_sids = [
        ('RRP 余额', 'RRP_BALANCE', 'Billion USD', rrp_override),
        ('10Y 收益率(日频YC10Y/决策)', 'YC10Y', '%', None),
        ('HY 信用利差', 'HY_OAS', '%', None),
        ('标普500', 'SP500', 'Index', None),
        ('VIX', 'VIX', 'Index', None),
        ('美元/日元', 'USD_JPY', 'Price', None),
        ('离岸人民币', 'USD_CNH', 'Price', None),
        ('铁矿石内盘', 'IRON_ORE_DOMESTIC', 'CNY', None),
        ('螺纹钢内盘', 'REBAR', 'CNY', None),
        ('市场广度20D动量', 'BREADTH_20D_MOMENTUM', '%', None),
        ('中国10Y', 'CN_10Y_YIELD', '%', None),
        ('日本10Y', 'JP_10Y', '%', None),
        ('德国10Y', 'DE_10Y', '%', None),
    ]
    input_snapshot = {}
    for name, sid, unit, override in audit_sids:
        d, v, lag, used_id, proxy_used = get_series_meta_full(sid, override_value=override)
        if v is not None:
            source_note = rrp_source_tag if name == 'RRP 余额' else ""
            proxy_note = f" [proxy={used_id}]" if proxy_used else ""
            print(f"    {name:24s}: {d} | 值 = {v:.4f} {unit}{source_note}{proxy_note}")
            input_snapshot[sid] = v
            if proxy_used:
                input_snapshot[f"{sid}_PROXY_USED"] = True
                input_snapshot[f"{sid}_USED_SERIES"] = used_id
        else:
            print(f"    {name:24s}: {d} | 值 = N/A")
            input_snapshot[sid] = None

    rt_date, us10y_rt, _ = get_series_meta('US10Y_RT_TRADEWEB')
    if us10y_rt is not None:
        print(f"    {'10Y 美债(盘中Tradeweb/参考)':24s}: {rt_date} | 值 = {us10y_rt:.3f} % [仅参考，不参与决策与利差]")
    else:
        print(f"    {'10Y 美债(盘中Tradeweb/参考)':24s}: N/A | 值 = N/A")

    print(f"{'─'*50}")
    try:
        cn10y_d, cn10y, cn_lag = get_series_meta('CN_10Y_YIELD')
        jp10y_d, jp10y, jp_lag = get_series_meta('JP_10Y')
        de10y_d, de10y, de_lag = get_series_meta('DE_10Y')
        us10y_d, us10y, us_lag = get_series_meta('YC10Y')
        if us10y and cn10y:
            if cn_lag <= 8: print(f"  [宏观联动] 中美10Y利差: {us10y - cn10y:+.2f}%")
            else: print(f"  [宏观联动] 中美10Y利差: 数据过期(中国滞后{cn_lag}天)，暂停计算")
        if us10y and jp10y:
            if jp_lag <= 8: print(f"  [宏观联动] 美日10Y利差: {us10y - jp10y:+.2f}%")
            else: print(f"  [宏观联动] 美日10Y利差: 数据过期(日本滞后{jp_lag}天)，暂停计算")
        if us10y and de10y:
            if de_lag <= 8: print(f"  [宏观联动] 美德10Y利差: {us10y - de10y:+.2f}%")
            else: print(f"  [宏观联动] 美德10Y利差: 数据过期(德国滞后{de_lag}天)，暂停计算")
        if us10y_rt is not None:
            print(f"  [盘中参考] 实时10Y Tradeweb = {us10y_rt:.3f}%")
        us2y_d, us2y, us2_lag = get_series_meta('YC2Y')
        ff_d, fedfunds, ff_lag = get_series_meta('FEDFUNDS')
        if us2y and fedfunds:
            diff_bp = (us2y - fedfunds) * 100
            direction = "倒挂/加息预期" if diff_bp > 0 else "降息预期"
            print(f"  [政策利率期限利差 PROXY] 2Y美债({us2y:.2f}%) - 联邦基金({fedfunds:.2f}%) = {diff_bp:+.1f}bp ({direction})")
            if ff_lag > 10:
                print(f"    ⚠️ 注：联邦基金数据滞后 {ff_lag} 天，该指标仅作宏观位置参考，不作为实时 FOMC 概率预判")
    except Exception:
        pass
    print(f"{'─'*50}")

    print(f"\n┌{'─'*58}┐\n│  【轨道2】Stress Overlay V2 (S0-S10)               │\n└{'─'*58}┘\n")
    stress = {}
    try:
        stress = stress_overlay_v2.evaluate_stress(asof)
        print(f"  当前压力状态: {stress['overall']}")
        print(f"  已触发层数: {stress['triggered_count']}/9")
        for l in stress['layers']:
            icon = '🚨' if l['triggered'] else '⏸️'
            print(f"  {icon} [{l['layer']}] {l['name']}")
    except Exception as e:
        print(f"  ⚠️ Stress异常: {e}")

    print(f"\n┌{'─'*58}┐\n│  【轨道3】多维度增强引擎                            │\n└{'─'*58}┘\n")

    from engines_v3.microstructure_trigger import compute_microstructure_trigger
    micro_res = compute_microstructure_trigger(asof)

    dollar_result = {}
    print("  [Dollar_Anchor] ", end='', flush=True)
    try:
        from engines_v3 import dollar_anchor
        with contextlib.redirect_stdout(io.StringIO()):
            dollar_result = dollar_anchor.compute_dollar_anchor(asof)
        print(f"{dollar_result.get('scenario_msg', 'N/A')}")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    chain_e_result = {}
    print("  [Chain_E]       ", end='', flush=True)
    try:
        from engines_v3 import transmission_graph
        with contextlib.redirect_stdout(io.StringIO()):
            trans = transmission_graph.compute_transmission(asof)
        for c in trans.get('chains', []):
            if 'Chain E' in c.get('name', ''):
                chain_e_result = c
                break
        if chain_e_result:
            print(f"{chain_e_result.get('status', 'N/A')} (激活度={chain_e_result.get('activation', 0):.3f})")
        else:
            print("N/A")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    cali_result = {}
    print("  [CALI]          ", end='', flush=True)
    try:
        from engines_v3 import cali_engine
        with contextlib.redirect_stdout(io.StringIO()):
            cali_result = cali_engine.compute_cali(asof)
        print(f"{cali_result.get('cali_score', 0):.1f}/100 ({cali_result.get('level', 'N/A')})")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    crowding_result = {}
    print("  [Crowding]      ", end='', flush=True)
    try:
        from engines_v3 import crowding_engine
        with contextlib.redirect_stdout(io.StringIO()):
            crowding_result = crowding_engine.compute_crowding(asof)
        print(f"{crowding_result.get('score', 0):.1f}/100 ({crowding_result.get('level', 'N/A')})")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    print(f"  [MicroTrigger]  {micro_res.get('status')} | 评分={micro_res.get('score')} | {micro_res.get('details')}")

    for name, fn in [
        ('Positioning', lambda: __import__('engines_v3.positioning_engine', fromlist=['evaluate_positioning']).evaluate_positioning(asof)),
        ('Velocity', lambda: __import__('engines_v3.velocity_engine', fromlist=['evaluate_velocity']).evaluate_velocity(asof)),
        ('Probability', lambda: __import__('engines_v3.probability_engine', fromlist=['evaluate_probability']).evaluate_probability(asof)),
        ('Contagion', lambda: __import__('engines_v3.contagion_engine', fromlist=['compute_contagion']).compute_contagion(asof)),
    ]:
        print(f"  [{name:12s}] ", end='', flush=True)
        try:
            if name == 'Probability':
                r = fn()
                p_r4_r5_val = r.get('high_risk_prob')
                prob_input_audit = r.get('input_audit', {})
                if p_r4_r5_val is not None:
                    print(f"       ↳ 最终概率 P(R4+R5)={p_r4_r5_val*100:.4f}%")
                else:
                    print(f"       ↳ ❌ 概率计算失败，返回 None")
            else:
                with contextlib.redirect_stdout(io.StringIO()):
                    r = fn()
                if name == 'Positioning':
                    print(f"Stress={r['positioning_stress']}/100 ({r['level']})")
                elif name == 'Velocity':
                    print(f"Breadth={r['breadth']['breadth_pct']}%")
                elif name == 'Contagion':
                    print(f"状态={r.get('status', 'N/A')}")
        except Exception as e:
            print(f"❌ {str(e)[:50]}")

    # ============ PROBABILITY_DECISION_ELIGIBILITY（基于 probability_engine 内证）============
    prob_engine_status = "COMPUTED" if p_r4_r5_val is not None else "FAILED"
    prob_input_health = prob_input_audit.get('input_health', 'UNKNOWN')
    prob_decision_eligible = prob_input_audit.get('decision_eligible', False)
    prob_decision_reason = prob_input_audit.get('decision_reason', 'UNKNOWN')
    prob_model_version = prob_input_audit.get('model_version', 'UNKNOWN')

    print("\n  [PROBABILITY_DECISION_ELIGIBILITY] (基于源码内证)")
    print(f"    ENGINE_STATUS             : {prob_engine_status}")
    print(f"    MODEL_VERSION             : {prob_model_version}")
    print(f"    INPUT_HEALTH              : {prob_input_health}")
    print(f"    DECISION_ELIGIBLE         : {prob_decision_eligible}")
    print(f"    DECISION_REASON           : {prob_decision_reason}")
    print(f"    INPUT_DEPENDENCY_SOURCE   : SOURCE_CODE_VERIFIED (probability_engine.py v6)")
    print(f"    NOT_REQUIRED_INPUTS       : {prob_input_audit.get('not_required_inputs', [])}")

    # ============ MODULE_DEPENDENCY_AUDIT ============
    print("\n  [MODULE_DEPENDENCY_AUDIT]")
    print(f"    GMS_REQUIRED_INPUTS           : INF / MON / FIS / LIQ / RISK")
    print(f"    RISK_GATE_REQUIRED_INPUTS     : GMS / INF_EXPECT / STRESS / FRAGILITY / PROBABILITY")
    print(f"    EVENT_SCENARIO_REQUIRED_INPUTS: MICH_1Y / SOFR / EFFR / HY_OAS")
    print(f"    SHADOW_MODE_REQUIRED_INPUTS   : RISK_GATE / EVENT / COVARIANCE / MOMENTUM")
    print(f"    LAYERED_FAIL_CLOSED           : True (每层独立检查)")

    # ============ DECISION_DATA_HEALTH ============
    critical_missing_inputs = []
    decision_degraded = False
    if 'INF_EXPECT' in missing_engines:
        critical_missing_inputs.append('INF_EXPECT (MICH_1Y STALE)')
        decision_degraded = True
    if p_r4_r5_val is None:
        critical_missing_inputs.append('PROBABILITY_ENGINE (FAILED)')
        decision_degraded = True
    elif not prob_decision_eligible:
        critical_missing_inputs.append(f'PROBABILITY_INELIGIBLE ({prob_decision_reason})')
        decision_degraded = True
    if not regime:
        critical_missing_inputs.append('GMS_REGIME (未返回)')
        decision_degraded = True

    global_data_health = _DATA_HEALTH.get('preflight', {}).get('verdict', 'UNKNOWN')
    decision_data_health = 'DEGRADED' if decision_degraded else 'HEALTHY'

    print("\n  [DECISION_DATA_HEALTH]")
    print(f"    GLOBAL_DATA_HEALTH              : {global_data_health}")
    print(f"    DECISION_DATA_HEALTH            : {decision_data_health}")
    print(f"    GMS_CORE_ENGINES                : {gms_health.get('valid_engines', 'N/A')}/5")
    print(f"    CRITICAL_MISSING_INPUTS         : {critical_missing_inputs if critical_missing_inputs else 'NONE'}")

    _DATA_HEALTH['decision'] = {
        'global_data_health': global_data_health,
        'decision_data_health': decision_data_health,
        'critical_missing_inputs': critical_missing_inputs,
        'probability': {
            'engine_status': prob_engine_status,
            'value': p_r4_r5_val,
            'input_health': prob_input_health,
            'decision_eligible': prob_decision_eligible,
            'decision_reason': prob_decision_reason,
            'model_version': prob_model_version,
            'input_dependency_source': 'SOURCE_CODE_VERIFIED',
            'not_required_inputs': prob_input_audit.get('not_required_inputs', []),
        },
    }

    if global_data_health == 'DEGRADED' or decision_degraded:
        final_audit_status = 'DEGRADED'
        print(f"  ⚠️ 最终数据自检: DEGRADED (全局WARN/决策层降级 覆盖原始 PASS)")
    else:
        final_audit_status = audit_status_raw
        print(f"  ✅ 最终数据自检: {final_audit_status}")

    print(f"\n┌{'─'*58}┐\n│  【轨道4】GMRE 4.1 智能层                            │\n└{'─'*58}┘\n")

    cu_spread_d, cu_spread, _ = get_series_meta('CU_SPREAD_PCT')
    if cu_spread:
        if abs(cu_spread) > 2.0:
            print(f"  [CU_CROSS_MARKET_EXTREME_SPREAD] 🚨 内外盘极值价差: {cu_spread:+.2f}% (逼仓风险)")
        else:
            print(f"  [CU_CROSS_MARKET_EXTREME_SPREAD] 🟢 内外盘价差: {cu_spread:+.2f}% (正常)")

    print("  [CAPS Commodity] ", end='', flush=True)
    try:
        from engines_v3 import caps_engine
        with contextlib.redirect_stdout(io.StringIO()):
            cu = caps_engine.compute_caps_risk("SHFE_COPPER")
            al = caps_engine.compute_caps_risk("SHFE_ALUMINUM")
        output_parts = []
        if cu: output_parts.append(f"铜 {'🚨' if cu['caps_score'] > 60 else '🟡'} {cu['caps_score']}")
        if al: output_parts.append(f"铝 {'🚨' if al['caps_score'] > 60 else '🟡'} {al['caps_score']}")
        print(" | ".join(output_parts))
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    print("  [LTI Clearing]  ", end='', flush=True)
    try:
        from engines_v3 import lti_engine
        with contextlib.redirect_stdout(io.StringIO()):
            lti = lti_engine.compute_lti(asof)
        icon = "🚨" if lti.get('level') in ("EXTREME", "HIGH") else "🟡" if lti.get('level') == "MEDIUM" else "🟢"
        raw_data = lti.get('raw', {})
        fr_diff_str = f"{raw_data.get('fr_cross_diff'):+.2f}%" if raw_data.get('fr_cross_diff') is not None else "N/A"
        hl_imb_str = f"{raw_data.get('hl_imbalance'):+.2f}%" if raw_data.get('hl_imbalance') is not None else "N/A"
        print(f"{icon} {lti.get('lti_score', 0)}/100 ({lti.get('level', 'UNKNOWN')}) | FR差异(相对) {fr_diff_str} | 持仓24H变幅 {hl_imb_str}")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    print(f"\n┌{'─'*58}┐\n│  【尾轨】尾部状态 + 预警 + 对冲                    │\n└{'─'*58}┘\n")
    tail_state = 'NORMAL'
    tail_adj = 1.0
    try:
        tail = yen_carry_state.update_state(asof)
        tail_state = tail['state']
        tail_adj = tail['risk_budget_adj']
        print(f"  尾部状态: {tail_state} | 风险预算调整: {tail_adj*100:.0f}%")
    except Exception as e:
        print(f"  ⚠️ 尾部状态机异常: {e}")

    print()
    try:
        alert_result = liquidity_alert.check_alerts(asof)
        valid_alerts = [a for a in alert_result['alerts'] if a['type'] != 'RRP_DATA_UNAVAILABLE']
        if len(valid_alerts) == 0:
            print("  ✅ 流动性预警: 无异常")
        else:
            print(f"  ⚠️ 触发 {len(valid_alerts)} 条预警:")
            for a in valid_alerts:
                print(f"    [{a['level']}] {a['type']}: {a['msg'][:70]}")
    except Exception as e:
        print(f"  ⚠️ 流动性预警异常: {e}")

    print()
    try:
        dau = dau_alert.check_alerts(asof)
        if 'error' not in dau:
            print(f"  DAU Z-score: {dau['z_score']:+.3f} | 最新={dau['latest']:,}")
    except Exception as e:
        print(f"  ⚠️ DAU异常: {e}")

    print()
    try:
        hedge = hedge_advisor.compute_hedge(asof)
        hedge_pct = hedge.get('total_hedge_pct', 0.0) * 100
        if hedge_pct > 0: print(f"  🛡️ 建议对冲: {hedge_pct:.1f}%")
        else: print("  ✅ 尾部对冲: 无需求")
    except Exception as e:
        print(f"  ⚠️ 对冲模块异常: {e}")

    print(f"\n┌{'─'*58}┐\n│  【执行】防线0-7                                    │\n└{'─'*58}┘\n")
    defense = {}
    try:
        defense = defense_v4.evaluate_v4(asof)
        print(f"  已突破防线: {defense['triggered_count']}/7 | 系统性危机: {'🚨 是' if defense['systemic_confirmed'] else '🟢 否'}\n")
        for l in defense['lines']:
            print(f"  {'🚨' if l['triggered'] else '⏸️'} [{l['line']}] {l['name']}")
    except Exception as e:
        print(f"  ⚠️ 防线异常: {e}")

    contagion_status = 'NORMAL'
    systemic_confirmed = defense.get('systemic_confirmed', False) if defense else False

    gate, gate_msg = compute_risk_gate(
        frag_level, stress.get('overall', ''), contagion_status, systemic_confirmed,
        p_r4_r5=p_r4_r5_val, missing_engines=missing_engines,
        prob_decision_eligible=prob_decision_eligible
    )

    print(f"\n┌{'─'*58}┐\n│  【最终】Risk Gate 风险等级                        │\n└{'─'*58}┘\n")
    print(f"  {gate_msg}\n  Risk Gate: {gate}")

    # ============ RISK_GATE_DEPENDENCY_CHECK ============
    print(f"\n  [RISK_GATE_DEPENDENCY_CHECK]")
    print(f"    GMS:             {'PASS' if regime else 'FAIL'} ({regime_label if regime else 'N/A'})")
    print(f"    INF_EXPECT:      {'FAIL' if 'INF_EXPECT' in missing_engines else 'PASS'}"
          f"{' (MICH_1Y STALE)' if 'INF_EXPECT' in missing_engines else ''}")
    print(f"    STRESS:          {'PASS' if stress else 'FAIL'} ({stress.get('overall', 'N/A') if stress else 'N/A'})")
    print(f"    FRAGILITY:       {'PASS' if frag_level != 'N/A' else 'FAIL'}")
    print(f"    PROBABILITY:     COMPUTED={p_r4_r5_val is not None}, DECISION_ELIGIBLE={prob_decision_eligible}")
    if not prob_decision_eligible:
        print(f"                     STATUS=FAIL, REASON={prob_decision_reason}")

    block_reasons = []
    if 'INF_EXPECT' in missing_engines:
        block_reasons.append('INF_EXPECT_STALE')
    if not prob_decision_eligible:
        block_reasons.append('PROBABILITY_INELIGIBLE')
    if not block_reasons and gate in ('RED', 'BLACK'):
        block_reasons.append(f'GATE_{gate}')

    print(f"    FINAL_GATE:      {gate}")
    print(f"    BLOCK_REASONS:   {block_reasons if block_reasons else 'NONE'}")

    dxy_pct = dollar_result.get('dxy_5y_pct') if dollar_result else None
    cali_score = cali_result.get('cali_score') if cali_result else None
    scenario = dollar_result.get('scenario', 'N/A') if dollar_result else 'N/A'
    try:
        phase_guide = get_dual_phase_guide(gate, frag_score_val, cali_score, scenario, dxy_pct)
        print(f"\n┌{'─'*58}┐\n│  【双阶段】宏观战略参考区间                        │\n└{'─'*58}┘\n")
        print(f"  {phase_guide['phase_emoji']} {phase_guide['phase']}")
        print(f"  💰 现金参考: {phase_guide['cash_recommendation']}")
        print(f"  🥇 黄金参考: {phase_guide['gold_recommendation']}")
        print(f"  💡 {phase_guide['note']}")
        print(f"  (注：该区间为宏观指导，实际执行以下方 Shadow Mode 权限为准)")
    except Exception as e:
        print(f"  ⚠️ 双阶段指南异常: {e}")

    print(f"\n┌{'─'*58}┐\n│  🚦 [Event Scenario] 事件情景推演与权限拦截        │\n└{'─'*58}┘")
    try:
        mock_cpi = None
        try:
            conn_cpi = sqlite3.connect(DB_PATH)
            try:
                cpi_series = load(conn_cpi, 'MICH_1Y_EXPECT', limit=1, verbose=False, strict_fresh=False)
                if not cpi_series.empty:
                    date_str = pd.to_datetime(cpi_series.index[-1]).strftime('%Y-%m-%d')
                    lag = (datetime.now() - pd.to_datetime(date_str)).days
                    if lag <= 45:
                        mock_cpi = float(cpi_series.iloc[-1])
                        print(f"  🔗 [Event Input] 当前采用的通胀预期(MICH_1Y): {mock_cpi:.2f}%")
                    else:
                        print(f"  ⚠️ [Event Input] MICH_1Y 数据过期(滞后{lag}天 > 45天)，数据作废")
                else:
                    print("  ⚠️ MICH_1Y_EXPECT 数据缺失，无法计算")
            finally:
                conn_cpi.close()
        except Exception as e:
            print(f"  ⚠️ 获取真实通胀数据失败: {e}")

        _, sofr_val, _ = get_series_meta('SOFR')
        _, effr_val, _ = get_series_meta('EFFR')
        _, hy_now, _ = get_series_meta('HY_OAS')

        hy_prev = 0.0
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute(
                "SELECT value FROM observations WHERE series_id='HY_SPREAD' "
                "ORDER BY timestamp DESC LIMIT 1 OFFSET 5"
            ).fetchone()
            if row: hy_prev = float(row[0])
            conn.close()
        except Exception:
            pass

        if sofr_val is not None and effr_val is not None:
            sofr_effr = (sofr_val - effr_val) * 100
        else:
            sofr_effr = 999

        hy_chg = (hy_now - hy_prev) if hy_prev and hy_now else 0
        cu_sp = cu_spread if cu_spread is not None else 0

        if mock_cpi is not None:
            perm, reason, is_contagion = evaluate_event_scenario(
                cpi_core_yoy=mock_cpi, sofr_effr_spread=sofr_effr, hy_spread_chg=hy_chg,
                cu_spread=cu_sp, lme_cu_5min_ret=None, margin_hike=False,
                is_event_day=False, minutes_since_release=9999
            )
            print(f"  当前权限判定: {perm.name}")
            print(f"  拦截原因: {reason}")
            print(f"  传染警报: {'🚨 是' if is_contagion else '🟢 否'}")
            event_perm_name, event_perm_reason = perm.name, reason
        else:
            print("  ⛔ [Event Input] 通胀预期数据过期，强制拦截。")
            event_perm_name, event_perm_reason = "BLOCK", "通胀预期数据过期"
    except Exception as e:
        print(f"  ❌ 事件引擎计算失败: {e}")
        event_perm_name, event_perm_reason = "BLOCK", f"引擎异常: {e}"

    print(f"\n┌{'─'*58}┐\n│  🧪 [Shadow Mode] 权限执行与风险预算底线            │\n└{'─'*58}┘")
    shadow_meta = {}
    try:
        from engines_v3.risk_budget_engine import compute_shadow_weights, get_shadow_meta
        shadow_weights = compute_shadow_weights(gate, event_perm_name, stress.get('overall', ''))
        shadow_meta = get_shadow_meta()
        if shadow_weights:
            log_dir = "logs"; os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "shadow_portfolio.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{asof}] Gate={gate} | Perm={event_perm_name} | Shadow_Weights={shadow_weights} | Meta={json.dumps(shadow_meta, ensure_ascii=False, sort_keys=True, default=str)}\n")
            print(f"  ✅ 影子权重已静默保存至 {log_file}")
    except Exception as e:
        print(f"  ⚠️ 影子引擎计算失败 (不影响主流程): {e}")

    print(f"\n  [RISK_BUDGET_AUDIT]")
    print(f"    TAIL_STATE                    : {tail_state}")
    print(f"    TAIL_RISK_BUDGET_MULTIPLIER   : {tail_adj*100:.0f}%")
    if shadow_meta:
        print(f"    PREVIOUS_BUDGET_CAP           : {shadow_meta.get('previous_cap', 0)*100:.1f}%")
        print(f"    STRESS_BUDGET_CAP             : {shadow_meta.get('max_capital_exposure', 0)*100:.1f}%")
        print(f"    EFFECTIVE_MAX_CAPITAL_EXPOSURE: {shadow_meta.get('max_capital_exposure', 0)*100:.1f}%")
        print(f"    FINAL_CAPITAL_EXPOSURE        : {shadow_meta.get('final_capital_exposure', 0)*100:.2f}%")
        print(f"    TARGET_VOLATILITY             : N/A (未实施)")
        print(f"    REALIZED_EST_VOLATILITY       : {shadow_meta.get('realized_est_volatility', 0)*100:.2f}%")
        print(f"    BTC_COVARIANCE_ELIGIBLE       : {shadow_meta.get('btc_covariance_eligible', True)}")
        print(f"    BTC_FORWARD_FILL_RATIO        : {shadow_meta.get('btc_forward_fill_ratio', 0)*100:.1f}%")
        if not shadow_meta.get('btc_covariance_eligible', True):
            print(f"    🚨 BTC_COVARIANCE_DEGRADED    : BTC 已从协方差矩阵剔除")

    try:
        from engines_v3.factor_attribution import compute_factor_attribution
        factor_res = compute_factor_attribution(asof, shadow_weights) if shadow_weights else {}
        fc_status = factor_res.get('status', 'N/A')
        fc_msg = factor_res.get('msg', 'N/A')
        print(f"  [FactorConc]    FACTOR_ATTR_PC1_STATUS: {fc_status} | {fc_msg}")
        print(f"  [FactorConc]    FACTOR_ATTR_PC1_SOURCE: factor_attribution.py (与 shadow_meta 的 PC1 口径不同)")
        if shadow_meta.get('market_pc1_share') is not None:
            print(f"  [FactorConc]    SHADOW_META_MARKET_PC1: {shadow_meta['market_pc1_share']*100:.1f}%")
        if shadow_meta.get('portfolio_pc1_share') is not None:
            print(f"  [FactorConc]    SHADOW_META_PORTFOLIO_PC1: {shadow_meta['portfolio_pc1_share']*100:.1f}%")
    except Exception as e:
        factor_res = {}
        print(f"  [FactorConc]    ❌ 因子归因失败: {str(e)[:50]}")

    _regime_display = "N/A"
    try:
        if p_r4_r5_val is not None:
            if p_r4_r5_val >= 0.50: _regime_display = f"R4/R5 (高危, P={p_r4_r5_val*100:.1f}%)"
            elif p_r4_r5_val >= 0.30: _regime_display = f"R3/R4 (警戒, P(R4+R5)={p_r4_r5_val*100:.1f}%)"
            elif regime: _regime_display = f"{regime.get('regime_label', 'N/A')} ({regime.get('confidence', 0)*100:.1f}%)"
        elif regime:
            _regime_display = f"{regime.get('regime_label', 'N/A')} ({regime.get('confidence', 0)*100:.1f}%)"
    except Exception:
        pass
    _frag_display = frag_level if frag_level != 'N/A' else "N/A"

    print(f"\n{'='*60}\n  GMRE 4.1 运行完成\n  Base Regime: {_regime_display} | Fragility: {_frag_display} | Risk Gate: {gate}\n{'='*60}\n")

    try:
        input_str = json.dumps(input_snapshot, sort_keys=True, default=str)
        input_hash = hashlib.sha256(input_str.encode('utf-8')).hexdigest()[:16]

        pred_state = {"regime": regime_label, "p_r4_r5": p_r4_r5_val, "gate": gate}
        pred_str = json.dumps(pred_state, sort_keys=True, default=str)
        prediction_hash = hashlib.sha256(pred_str.encode('utf-8')).hexdigest()[:16]

        run_state = {
            "asof": asof,
            "data_health": _DATA_HEALTH.get('preflight', {}),
            "decision_health": _DATA_HEALTH.get('decision', {}),
            "eligibility": {k: v[0] for k, v in _DATA_ELIGIBILITY.items()},
            "regime": regime_label,
            "regime_health": regime.get('health', {}) if regime else {},
            "stress": stress.get('overall', 'NONE'),
            "fragility": frag_level,
            "defense_triggered": defense.get('triggered_count', 0) if defense else None,
            "event_perm": event_perm_name,
            "shadow_weights": shadow_weights,
            "shadow_meta": shadow_meta,
            "engine_fusion": {
                "MON_BASE_Z": engine_z_values.get('MON'),
                "MON_V2_COMPOSITE": mon_v2_comp,
                "FIS_BASE_Z": engine_z_values.get('FIS'),
                "FIS_V2_COMPOSITE": fis_v2_comp,
            },
            "tail_state": tail_state,
            "tail_adj": tail_adj,
        }
        run_snapshot_str = json.dumps(run_state, sort_keys=True, default=str)
        run_snapshot_hash = hashlib.sha256(run_snapshot_str.encode('utf-8')).hexdigest()[:16]

        code_commit = get_git_commit()
        conn = sqlite3.connect(DB_PATH)
        conn.execute("CREATE TABLE IF NOT EXISTS daily_summary (asof_date TEXT PRIMARY KEY, risk_gate TEXT, stress_state TEXT, frag_level TEXT)")
        conn.execute("INSERT OR REPLACE INTO daily_summary (asof_date, risk_gate, stress_state, frag_level) VALUES (?, ?, ?, ?)", (asof, gate, stress.get('overall', 'NONE'), frag_level))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions_log (
                forecast_date TEXT PRIMARY KEY,
                model_version TEXT,
                code_commit TEXT,
                input_snapshot_hash TEXT,
                regime TEXT,
                p_r4_r5 REAL,
                fragility_score REAL,
                risk_gate TEXT,
                data_quality_state TEXT,
                details_json TEXT
            )
        """)

        details = {
            "regime": regime,
            "regime_health": regime.get('health', {}) if regime else {},
            "stress": stress.get('overall', 'NONE'),
            "fragility_level": frag_level,
            "gate_msg": gate_msg,
            "p_r4_r5": p_r4_r5_val,
            "dollar_anchor": dollar_result.get('scenario') if dollar_result else None,
            "cali_score": cali_result.get('cali_score') if cali_result else None,
            "crowding_score": crowding_result.get('score') if crowding_result else None,
            "micro_trigger": micro_res,
            "shadow_weights": shadow_weights,
            "shadow_meta": shadow_meta,
            "factor_concentration": factor_res,
            "engine_fusion": {
                "MON_BASE_Z": engine_z_values.get('MON'),
                "MON_V2_COMPOSITE": mon_v2_comp,
                "FIS_BASE_Z": engine_z_values.get('FIS'),
                "FIS_V2_COMPOSITE": fis_v2_comp,
            },
            "tail_state": tail_state,
            "tail_adj": tail_adj,
            "data_audit": {"status": final_audit_status, "raw_status": audit_status_raw},
            "data_health": _DATA_HEALTH.get('preflight', {}),
            "decision_health": _DATA_HEALTH.get('decision', {}),
            "data_eligibility": {k: v for k, v in _DATA_ELIGIBILITY.items()},
            "event_interceptor": {"perm": event_perm_name, "reason": event_perm_reason},
            "block_reasons": block_reasons,
            "probability_input_audit": prob_input_audit,
            "prediction_hash": prediction_hash,
            "run_snapshot_hash": run_snapshot_hash,
            "pipeline_status": "COMPLETED",
            "prediction_archive_status": "OK",
            "git_commit": code_commit,
        }

        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO predictions_log
            (forecast_date, model_version, code_commit, input_snapshot_hash,
             regime, p_r4_r5, fragility_score, risk_gate, data_quality_state, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            asof, 'GMRE_4.1', code_commit, input_hash,
            regime_label, p_r4_r5_val, frag_score_val, gate, final_audit_status,
            json.dumps(details, ensure_ascii=False, default=str)
        ))
        conn.commit()
        conn.close()

        print("✅ [P0-B] 预测日志已归档")
        print(f"    pipeline_status          : COMPLETED")
        print(f"    prediction_archive_status: OK")
        print(f"    input_hash               : {input_hash}")
        print(f"    prediction_hash          : {prediction_hash}")
        print(f"    run_snapshot_hash        : {run_snapshot_hash}")
        print(f"    git_commit               : {code_commit}")

    except Exception as e:
        print("❌ [P0-B] 预测日志归档失败")
        print(f"    pipeline_status          : COMPLETED")
        print(f"    prediction_archive_status: FAILED")
        print(f"    archive_error            : {e}")


def guarded_main():
    try:
        main()
        return 0
    except DataError as e:
        return handle(e)


if __name__ == "__main__":
    raise SystemExit(guarded_main())