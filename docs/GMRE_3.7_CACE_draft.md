\# GMRE 3.7 · Cross-Asset Correlation Engine (CACE) 设计草案



\*\*版本\*\*：v0.1 draft

\*\*日期\*\*：2026-10-08

\*\*状态\*\*：设计输入，10-21 后实施

\*\*性质\*\*：宏观状态识别框架 · 学术研究 · 非交易建议



\---



\## 0. 设计哲学



\*\*核心原则\*\*：CACE 只做\*\*跨资产关系标注\*\*，不做\*\*方向预测\*\*。

GMRE 现有：识别状态（R/S/F）

CACE 新增：标注跨资产关系（相关性/流动性/机构流向）

不越界： 不预测价格、不预判拐点、不给交易信号



text



\*\*与 Constitution 的关系\*\*：

\- Rule 5：Macro Regime ≠ Asset Regime → CACE 明确区分宏观与资产层

\- Rule 9：Every Conclusion Requires Evidence → CACE 每个信号都有数据支撑

\- Rule 12：Model Uncertainty Must Be Explicit → CACE 输出带置信度



\---



\## 1. 模块定位



\### 1.1 为什么需要 CACE



\*\*当前 GMRE 3.3 的盲区\*\*：



| 现有模块 | 覆盖范围 | 缺口 |

|---|---|---|

| RISK 引擎 | VIX / HY / USD | 无跨资产相关性 |

| CRYPTO 引擎 | BTC/ETH 7D/24H | 无对标资产 |

| CRYPTO\_CHAIN | DAU | 无稳定币供应动态 |

| MKT\_STRUCT | 交易所价格 | 无 ETF 流入 |



\*\*核心缺口\*\*：GMRE 知道 BTC 的绝对表现，但不知道 BTC 相对于其他资产的"相对位置"。



\### 1.2 模块目标



\*\*新增引擎\*\*：Cross-Asset Correlation Engine (CACE)



\*\*三个子维度\*\*：



| 子维度 | 输入 | 输出 |

|---|---|---|

| \*\*A. 跨资产相关性\*\* | BTC vs NDX/GOLD/DXY/TLT | 相关系数矩阵 |

| \*\*B. 稳定币流动性\*\* | USDT/USDC 净供应变化 | 流动性敏感度 |

| \*\*C. ETF 机构流向\*\* | BTC/ETH ETF 日流入 | 机构情绪指数 |



\### 1.3 与 GMRE 现有框架的关系

Cross-Asset Correlation Engine (CACE)

↓ 输出 3 个子维度

↓

接入 RISK 引擎（扩展）

接入 LIQ 引擎（扩展）

接入 CRYPTO 引擎（扩展）

接入 CRSI（新增维度）

↓

影响 R / S / F 状态机



text



\---



\## 2. 子维度 A：跨资产相关性



\### 2.1 对标资产



| 资产 | 代码 | 数据源 | 意义 |

|---|---|---|---|

| 纳斯达克100 | NDX | Yahoo/AKShare | 科技股风险偏好 |

| 标普500 | SPX | 本地已有 | 广义美股 |

| 黄金 | GOLD | FRED/飞书 | 抗通胀/避险 |

| 美元指数 | DXY | 本地已有 | 美元强弱 |

| 10Y 美债 | TLT/10Y | 本地已有 | 利率 |

| BTC | BTC | 本地已有 | 目标资产 |



\### 2.2 相关性窗口



| 窗口 | 用途 |

|---|---|

| 20 天 | 短期相关性（周级别）|

| 60 天 | 中期相关性（季度级别）|

| 120 天 | 长期相关性（半年级别）|



\### 2.3 关键指标定义



```python

CrossAssetCorr = {

&#x20;   "btc\_ndx\_20d": float,      # BTC 与纳指 20 日相关性

&#x20;   "btc\_ndx\_60d": float,      # BTC 与纳指 60 日相关性

&#x20;   "btc\_gold\_20d": float,     # BTC 与黄金 20 日相关性

&#x20;   "btc\_dxy\_20d": float,      # BTC 与美元 20 日相关性

&#x20;   "btc\_tlt\_20d": float,      # BTC 与美债 20 日相关性



&#x20;   # 派生信号

&#x20;   "btc\_vs\_tech\_divergence": float,   # BTC 与科技股背离度

&#x20;   "risk\_regime": str,                 # RISK\_ON / NEUTRAL / RISK\_OFF

&#x20;   "corr\_regime": str,                 # CORRELATED / DECOUPLED / DIVERGENT

}

2.4 信号解读

状态	条件	含义

RISK\_ON	BTC\_NDX\_20d > 0.5 且 BTC 上涨	加密与科技同涨

RISK\_OFF	BTC\_NDX\_20d > 0.5 且 BTC 下跌	加密与科技同跌

DECOUPLED	|BTC\_NDX\_20d| < 0.3	加密独立行情

DIVERGENT	BTC\_NDX\_20d < -0.3	加密与科技反向

2.5 关键观察（来自 2026-10-08 分析）

BTC 与 NDX 保持中度正相关（约 0.55-0.65）



对加密内部流动性（USDT/USDC 净供应变化）的敏感度明显提升



现货 ETF 资金流向继续作为机构盘面主控变量



3\. 子维度 B：稳定币流动性

3.1 数据源

数据源	频率	内容

DefiLlama	每小时	USDT/USDC 总供应

CoinGecko	每小时	稳定币市值

链上 API	实时	铸造/销毁事件

CryptoQuant	日度	交易所净流

3.2 关键指标

python

StablecoinFlow = {

&#x20;   "usdt\_supply": float,           # USDT 总量（十亿美元）

&#x20;   "usdc\_supply": float,           # USDC 总量

&#x20;   "total\_stable": float,          # 总量



&#x20;   "usdt\_24h\_change": float,       # 24h 变化

&#x20;   "usdt\_7d\_change": float,        # 7d 变化

&#x20;   "usdt\_30d\_change": float,       # 30d 变化



&#x20;   "net\_issuance\_7d": float,       # 7d 净发行

&#x20;   "net\_issuance\_30d": float,      # 30d 净发行



&#x20;   "exchange\_inflow": float,       # 流入交易所

&#x20;   "exchange\_outflow": float,      # 流出交易所

&#x20;   "exchange\_net": float,          # 净流入（买入信号）

}

3.3 信号解读

状态	条件	含义

STRONG\_INFLOW	30d 净发行 > +5%	场外资金大举进场

MILD\_INFLOW	30d 净发行 > +1%	温和流入

NEUTRAL	|30d 净发行| < 1%	稳定

MILD\_OUTFLOW	30d 净发行 < -1%	温和流出

STRONG\_OUTFLOW	30d 净发行 < -5%	场外资金离场

3.4 当前数据（2026-10-07）

稳定币总市值：$312.6B



1d：+0.21B



7d：+1.60B



30d：+3.91B



状态：MILD\_INFLOW



4\. 子维度 C：ETF 机构流向

4.1 数据源

数据源	频率	内容

Farside	每日	BTC/ETH ETF 净流入

Bloomberg	每日	机构持仓（付费）

SEC 13F	季度	机构持仓（滞后）

4.2 关键指标

python

ETFFlow = {

&#x20;   "btc\_etf\_daily": float,         # 日流入（百万美元）

&#x20;   "btc\_etf\_7d": float,            # 7d 累计

&#x20;   "btc\_etf\_30d": float,           # 30d 累计



&#x20;   "eth\_etf\_daily": float,

&#x20;   "eth\_etf\_7d": float,



&#x20;   "btc\_etf\_streak": int,          # 连续流入/流出天数



&#x20;   # 派生

&#x20;   "institutional\_regime": str,    # ACCUMULATION / DISTRIBUTION / NEUTRAL

&#x20;   "flow\_momentum": float,         # 流入动量

}

4.3 信号解读

状态	条件	含义

STRONG\_ACCUMULATION	30d 流入 > +$3B	机构大举建仓

MILD\_ACCUMULATION	30d 流入 > +$1B	温和建仓

NEUTRAL	30d 在 ±$1B 之间	观望

MILD\_DISTRIBUTION	30d 流出 > $1B	温和减仓

STRONG\_DISTRIBUTION	30d 流出 > $3B	机构大举减仓

4.4 当前数据（2026-10-06）

BTC ETF 日流入：$118.8M（Farside）



10-02 至 10-06 累计约 $342M



状态：MILD\_ACCUMULATION



5\. CACE 完整设计

5.1 模块结构

text

engines\_v3/cross\_asset\_correlation.py

├── CrossAssetCorr    # 子模块 A：跨资产相关性

├── StablecoinFlow    # 子模块 B：稳定币流动性

└── ETFFlow          # 子模块 C：ETF 机构流向

5.2 输出结构

json

{

&#x20; "asof": "2026-10-08",

&#x20; "cross\_asset": {

&#x20;   "btc\_ndx\_20d": 0.62,

&#x20;   "btc\_ndx\_60d": 0.55,

&#x20;   "btc\_gold\_20d": -0.15,

&#x20;   "btc\_dxy\_20d": -0.42,

&#x20;   "btc\_tlt\_20d": 0.28,

&#x20;   "regime": "RISK\_ON\_CORRELATED",

&#x20;   "divergence\_score": 0.15

&#x20; },

&#x20; "stablecoin": {

&#x20;   "total\_supply": 312.6,

&#x20;   "net\_issuance\_30d": 3.91,

&#x20;   "exchange\_net": -0.5,

&#x20;   "regime": "MILD\_INFLOW"

&#x20; },

&#x20; "etf\_flow": {

&#x20;   "btc\_30d": 1200,

&#x20;   "eth\_30d": 350,

&#x20;   "streak": 3,

&#x20;   "regime": "MILD\_ACCUMULATION"

&#x20; },

&#x20; "composite\_score": 0.35,

&#x20; "confidence": 0.72

}

5.3 综合评分算法

python

def compute\_composite\_score(cross\_asset, stablecoin, etf\_flow):

&#x20;   # 权重（可调）

&#x20;   W\_CORR = 0.30

&#x20;   W\_STABLE = 0.30

&#x20;   W\_ETF = 0.40



&#x20;   # 子分（-1 到 +1）

&#x20;   corr\_score = map\_corr\_to\_score(cross\_asset)

&#x20;   stable\_score = map\_stable\_to\_score(stablecoin)

&#x20;   etf\_score = map\_etf\_to\_score(etf\_flow)



&#x20;   # 加权

&#x20;   composite = (W\_CORR \* corr\_score +

&#x20;                W\_STABLE \* stable\_score +

&#x20;                W\_ETF \* etf\_score)



&#x20;   # 置信度

&#x20;   confidence = compute\_confidence(\[cross\_asset, stablecoin, etf\_flow])



&#x20;   return composite, confidence

6\. 数据源清单

6.1 新增数据源

\#	数据源	频率	用途	优先级

1	NDX 指数	日度	BTC-NDX 相关性	P0

2	USDT 供应量	每小时	稳定币流动性	P0

3	USDC 供应量	每小时	稳定币流动性	P0

4	稳定币交易所净流	日度	买卖压力	P1

5	BTC ETF 日流入	日度	机构情绪	P0

6	ETH ETF 日流入	日度	机构情绪	P1

7	黄金实时价	日度	避险相关性	P0

8	TLT（20Y+ 美债 ETF）	日度	利率敏感性	P1

6.2 数据源实施方式

数据源	获取方式

NDX	Yahoo Finance / AKShare

USDT/USDC	DefiLlama API

稳定币交易所净流	CryptoQuant / Glassnode

BTC/ETH ETF	Farside

GOLD	FRED / Yahoo

TLT	Yahoo

7\. 与 GMRE 主引擎的接入点

7.1 接入 RISK 引擎（扩展）

当前 RISK 引擎：VIX / HY / USD



扩展后：



python

RISK = {

&#x20;   "vix": ...,

&#x20;   "hy\_spread": ...,

&#x20;   "usd": ...,

&#x20;   # 新增

&#x20;   "btc\_ndx\_corr": ...,      # 跨资产相关性

&#x20;   "risk\_regime": ...,        # RISK\_ON / RISK\_OFF

}

7.2 接入 LIQ 引擎（扩展）

当前 LIQ 引擎：WALCL / RRP / TGA



扩展后：



python

LIQ = {

&#x20;   "walcl": ...,

&#x20;   "rrp": ...,

&#x20;   "tga": ...,

&#x20;   # 新增

&#x20;   "stablecoin\_supply": ...,      # 稳定币总量

&#x20;   "stablecoin\_net\_issuance": ..., # 净发行

&#x20;   "exchange\_net\_flow": ...,       # 交易所净流

}

7.3 接入 CRYPTO 引擎（扩展）

当前 CRYPTO 引擎：BTC/ETH 7D/24H



扩展后：



python

CRYPTO = {

&#x20;   "btc\_7d": ...,

&#x20;   "eth\_7d": ...,

&#x20;   # 新增

&#x20;   "etf\_flow\_regime": ...,        # ACCUMULATION / DISTRIBUTION

&#x20;   "etf\_flow\_momentum": ...,       # 流入动量

&#x20;   "cross\_asset\_regime": ...,      # RISK\_ON / RISK\_OFF

}

7.4 接入 CRSI（新增维度）

CRSI 新增 3 个维度：



python

CRSI = {

&#x20;   "Macro Risk": ...,

&#x20;   "Liquidity Risk": ...,

&#x20;   "Leverage Risk": ...,

&#x20;   "Derivatives Risk": ...,

&#x20;   "Stablecoin Risk": ...,

&#x20;   "Exchange Risk": ...,

&#x20;   "On-chain Risk": ...,

&#x20;   "Contagion Risk": ...,

&#x20;   # 新增

&#x20;   "Cross-Asset Risk": ...,        # 跨资产相关性崩塌

&#x20;   "Institutional Flow Risk": ..., # ETF 大规模流出

&#x20;   "Stablecoin Flow Risk": ...,    # 稳定币大规模赎回

}

7.5 接入 Transmission Chain

新增 Chain G：跨资产传导



text

Fed → NDX → BTC

&#x20; ↓

BTC 与 NDX 相关性上升 → 加密被纳入"科技股篮子"

&#x20; ↓

NDX 下跌 → BTC 同步下跌

Chain G 触发条件：



BTC\_NDX\_20d > 0.6 且 NDX 5D < -3%



或 BTC\_NDX\_20d < -0.3（背离）



7.6 接入 Crisis Fingerprint

新增指纹：CORRELATION\_COLLAPSE



定义：跨资产相关性在短期内剧烈变化



20D 相关性从 <0.3 跳到 >0.7



或从 >0.7 跳到 <0.3



历史先例：



2020-03 COVID：所有资产相关性 → 1



2022-06 Rate Shock：BTC 与 NDX 相关性 → 0.7



8\. 实施路线图（10-21 后）

阶段	时间	任务

阶段 1	10-21 → 11-07	设计 CACE 完整规格

阶段 2	11-07 → 11-21	数据源接入（NDX/USDT/USDC/ETF）

阶段 3	11-21 → 12-05	CACE 引擎开发

阶段 4	12-05 → 12-19	与 GMRE 主引擎集成

阶段 5	12-19 → 01-16	历史回测 + 校准

总时间：约 3 个月（含 GMRE 3.6 学术模块并行）。



9\. 关键洞察

9.1 为什么跨资产相关性重要

GMRE 3.3 的局限：只看 BTC 本身，不知道 BTC 在资产网络中的位置。



CACE 的价值：



如果 BTC 与 NDX 高度相关 → 加密不是独立资产，是"科技股的高 Beta 版本"



如果 BTC 与 GOLD 高度相关 → 加密是"数字黄金"



如果 BTC 与 DXY 高度负相关 → 加密是"美元反向资产"



这三种状态下的风险含义完全不同。



9.2 为什么稳定币流动性重要

稳定币是加密市场的"现金"：



稳定币净发行增加 → 场外资金进场



稳定币净发行减少 → 场外资金离场



交易所净流入增加 → 买盘压力



交易所净流出增加 → 卖盘压力



这是加密市场独有的"流动性领先指标"。



9.3 为什么 ETF 机构流向重要

ETF 是加密市场的"机构入场券"：



2024 年 BTC ETF 通过后，机构资金通过 ETF 进入



ETF 流入是机构情绪的最直接代理



ETF 流出可能引发连锁反应（赎回 → 卖出 → 价格下跌）



当前（2026-10）：ETF 流入是"机构盘面主控变量"。



10\. 待确认项

\#	项目	状态

1	NDX 数据源（Yahoo vs AKShare）	待评估

2	稳定币交易所净流数据源（CryptoQuant vs Glassnode）	待评估

3	TLT vs 10Y 收益率的选择	待定

4	相关性窗口（20/60/120）是否足够	待回测

5	综合评分的权重（0.30/0.30/0.40）	待优化

6	是否引入 ETH 对标（ETH/BTC 相关性）	待评估

11\. 参考数据（2026-10-08）

跨资产相关性（估算）

资产对	20D 相关性	60D 相关性

BTC-NDX	+0.62	+0.55

BTC-GOLD	-0.15	-0.20

BTC-DXY	-0.42	-0.38

BTC-TLT	+0.28	+0.25

稳定币流动性

指标	值

总市值	$312.6B

1d 变化	+0.21B

7d 变化	+1.60B

30d 变化	+3.91B

状态	MILD\_INFLOW

ETF 机构流向

指标	值

BTC ETF 日流入（10-06）	$118.8M

BTC ETF 30d 累计	约 $1.2B

ETH ETF 30d 累计	约 $0.35B

状态	MILD\_ACCUMULATION

12\. 一句话总结

CACE 补上了 GMRE 的三个盲区：



跨资产相关性——BTC 相对于美股/黄金/美元的位置



稳定币流动性——场外资金进出



ETF 机构流向——机构情绪



三者合起来，让 GMRE 从"看 BTC 本身"扩展到"看 BTC 在整个资产网络中的位置"。



10-21 后作为 GMRE 3.7 的一部分实施。

