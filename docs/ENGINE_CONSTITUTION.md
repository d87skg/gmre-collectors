\# GMRE ENGINE CONSTITUTION



\## 12条铁律



\### Rule 1: NO\_DATA ≠ ZERO\_RISK

缺少数据时，输出 NO\_DATA 或 UNKNOWN，绝不输出 0。



\### Rule 2: RRP depletion ≠ Liquidity Crisis

RRP耗尽只是 Buffer Depletion，不是 Funding Crisis。

必须经过 S5 FUNDING\_STRESS 确认。



\### Rule 3: Market Pricing ≠ Policy Decision

CME FedWatch 是市场预期，不是美联储决定。分开记录。



\### Rule 4: GMS ≠ Probability

GMS 是 Regime Score（距离映射），Bayesian 才是 Posterior Probability。



\### Rule 5: Macro Regime ≠ Asset Regime

宏观状态不等于资产状态，中间需要 Financial Regime 层。



\### Rule 6: Warning ≠ Confirmation

任何单指标只能产生 WARNING，不能产生 CONFIRMED。



\### Rule 7: Single Indicator Cannot Trigger Systemic

系统性危机必须跨层确认（Funding + Credit + Contagion）。



\### Rule 8: Backtest Must Be PIT-Aware

回测禁止使用 future data，必须用 pit.get\_series\_asof()。



\### Rule 9: Every Conclusion Requires Evidence

每个结论必须可追溯到 Observation → Source → PIT → Hash。



\### Rule 10: Every Regime Requires Invalidation

每个 Regime 判断必须定义失效条件。



\### Rule 11: No Hindsight Data Leakage

禁止用修正后的数据倒推历史判断。



\### Rule 12: Model Uncertainty Must Be Explicit

当 R2/R3/R4 概率相近（差距<15%）时，必须标记 HIGH\_UNCERTAINTY。

