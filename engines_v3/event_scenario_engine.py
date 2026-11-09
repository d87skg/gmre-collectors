# -*- coding: utf-8 -*-
"""
engines_v3/event_scenario_engine.py
事件情景推演引擎 —— Hard Interceptor（拦截器，不修改目标权重，只控制执行权限）
优先级：event_scenario_engine > Risk Gate > Fragility > portfolio optimizer
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from enum import IntFlag, auto
from typing import Tuple, Dict, Optional

# ===================== 权限掩码（位标志） =====================
class TradePerm(IntFlag):
    NONE = 0                # 禁止所有新订单
    REDUCE = auto()         # 仅允许：减仓、止盈、止损（预先挂单）
    BUY_TREASURY = auto()   # 短债 / 长债（TLT / SHY）
    BUY_GOLD = auto()       # 黄金
    BUY_RISK = auto()       # BTC / SPX / 风险权益
    ALL = REDUCE | BUY_TREASURY | BUY_GOLD | BUY_RISK

# ===================== 配置常量 =====================
CFG = {
    "CPI_LOCK_FIRST_MIN": 60,
    "CPI_LIMIT_MIN": 240,
    "STABILIZE_SECONDS": 600,  # 指标需要持续达标 10min
    "THRESHOLD_CORE_CPI_HIGH": 4.1,
    "THRESHOLD_CORE_CPI_LOW": 3.5,
    "THRESHOLD_SOFR_EFFR": 5.0,  # bp
    "THRESHOLD_HY_SPREAD_CHG": 0.5,  # 5日变动 %
    "THRESHOLD_CU_SPREAD": 10.0,  # %
    "THRESHOLD_LME_COPPER_DN": -2.5,  # 5min 回撤阈值
}

# ===================== 内部状态防抖快照 =====================
_snapshot_cache: Dict[str, Dict] = {}

def check_contagion(sofr_effr_spread: float, hy_spread_chg: float, lme_cu_5min_ret: float) -> bool:
    """全局传染触发器：真正跨资产流动性踩踏"""
    return (sofr_effr_spread > CFG["THRESHOLD_SOFR_EFFR"] and
            hy_spread_chg > CFG["THRESHOLD_HY_SPREAD_CHG"] and
            lme_cu_5min_ret < CFG["THRESHOLD_LME_COPPER_DN"])

def cu_is_local_only(cu_spread: float, lme_cu_5min_ret: float, margin_hike: bool) -> bool:
    """True = 仅上期所局部逼仓解套，不是宏观传染"""
    if margin_hike: return True
    if cu_spread < CFG["THRESHOLD_CU_SPREAD"] and lme_cu_5min_ret > CFG["THRESHOLD_LME_COPPER_DN"]:
        return True
    return False

def evaluate_event_scenario(
    cpi_core_yoy: float,
    sofr_effr_spread: float,
    hy_spread_chg: float,
    cu_spread: float,
    lme_cu_5min_ret: float,
    margin_hike: bool = False,
    is_event_day: bool = True,
    minutes_since_release: int = 9999
) -> Tuple[TradePerm, str, bool]:
    """
    主情景评估入口。
    返回：(perm:TradePerm, reason:str, contagion:bool)
    """
    contagion = check_contagion(sofr_effr_spread, hy_spread_chg, lme_cu_5min_ret)
    cu_local = cu_is_local_only(cu_spread, lme_cu_5min_ret, margin_hike)

    base_perm = TradePerm.REDUCE
    reason_parts = []

    # ---------------- 事件窗口时间锁 ----------------
    if is_event_day:
        if minutes_since_release <= CFG["CPI_LOCK_FIRST_MIN"]:
            return TradePerm.REDUCE, f"⏱️ 事件窗口：数据发布后前 {CFG['CPI_LOCK_FIRST_MIN']} 分钟，冻结所有新建买入。", contagion
        elif minutes_since_release <= CFG["CPI_LIMIT_MIN"]:
            base_perm = TradePerm.REDUCE
            reason_parts.append(f"⏱️ 事件窗口：60–240分钟，加仓通道默认锁定")

    # ---------------- 三条CPI情景 ----------------
    if cpi_core_yoy > CFG["THRESHOLD_CORE_CPI_HIGH"]:
        if contagion:
            perm = TradePerm.REDUCE
            reason = "🚨 流动性踩踏确认：核心CPI爆表 + SOFR/信用/伦铜共振，禁止一切新建风险敞口。"
        else:
            perm = TradePerm.REDUCE
            reason = "🟠 CPI爆表，但无跨资产传染；等待隔夜确认，禁止新开多头。"

    elif cpi_core_yoy < CFG["THRESHOLD_CORE_CPI_LOW"]:
        if hy_spread_chg <= 0 and not cu_local and not contagion:
            perm = TradePerm.REDUCE | TradePerm.BUY_TREASURY | TradePerm.BUY_GOLD
            reason = "🟢 CPI降温，信用平稳，无铜局部逼仓/传染；放行长债、黄金，权益/加密禁止。"
        else:
            perm = TradePerm.REDUCE
            reason = "🟡 CPI降温，但跨资产指标异常；流动性风险未解除，继续观望，禁止加仓。"
    else:
        perm = TradePerm.REDUCE
        reason = "⚪ CPI落在中性震荡区间：多空双杀，冻结所有新建买入。"

    if reason_parts:
        reason = "; ".join(reason_parts) + " | " + reason
        
    return perm, reason, contagion