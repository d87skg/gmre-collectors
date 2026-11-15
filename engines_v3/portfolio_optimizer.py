# -*- coding: utf-8 -*-
"""engines_v3/portfolio_optimizer.py - DEPRECATED (v6.0)

═══════════════════════════════════════════════════════════════
  ⚠️ 本模块的所有权重计算能力已永久停止。
  ⚠️ 权重真相唯一来源：engines_v3.risk_budget_engine.compute_shadow_weights()
  ⚠️ 主流程 run_v4.py 已不再 import 本模块。
═══════════════════════════════════════════════════════════════

  历史遗留缺陷（审计报告 v2 已记录，不再修复）：
    1. SQL 用 ORDER BY ASC LIMIT 30，取到的是最早样本，不是最新；
    2. BTC(1H) 与 GOLD/SHY(日频) 混算波动率，统计周期不一致；
    3. target_vol 在归一化后被数学抵消，实际未实现波动率控制；
    4. 缺失资产默认填 0.02 波动率，可能反向抬高其权重；
    5. get_data_health() 对“完全无记录”的序列不报异常，可能导致“缺失即健康”。

  本文件的 get_portfolio_advice / get_data_health 仅作为历史 import 兼容占位。
  任何新代码必须直接调用 risk_budget_engine，或读取 predictions_log.details_json。
"""

DEPRECATED = True
DEPRECATION_REASON = "USE risk_budget_engine.compute_shadow_weights"


def get_portfolio_advice(gate_state, frag_score, caps_cu=0.0):
    """【已废弃】仅为旧 tools 脚本 import 兼容，永远返回空仓 + 100% 现金。"""
    return {}, 100.0


def get_data_health():
    """【已废弃】数据健康统一由 core/errors.py 的 preflight() 判定。"""
    return "已由 data_proxy / preflight 统一接管"