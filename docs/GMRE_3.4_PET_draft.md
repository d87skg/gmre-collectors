markdown

\# GMRE 3.4 · Policy Event Tracker (PET) 设计草案



\*\*版本\*\*：v0.1 draft

\*\*日期\*\*：2026-10-04

\*\*状态\*\*：设计输入，10-21 后实施

\*\*性质\*\*：宏观状态识别框架 · 学术研究 · 非交易建议



\---



\## 0. 设计哲学



\*\*核心原则\*\*：PET 只做\*\*事件特征标注\*\*，不做\*\*结果预测\*\*。

GMRE 现有：识别状态（R/S/F）

PET 新增：标注事件（量级/持续性/可信度/反噬风险）

不越界： 不预测价格、不预判拐点、不给交易信号



text



\*\*与 Constitution 的关系\*\*：

\- Rule 3：Market Pricing ≠ Policy Decision → 明确区分"政策意图"和"市场定价"

\- Rule 6：Warning ≠ Confirmation → 只输出事件特征，等市场确认

\- Rule 10：Every Regime Requires Invalidation → 每个事件都有失效条件



\---



\## 1. 政策事件分类（10 大类）



\### 1.1 能源/大宗商品类



| 子类 | 触发条件 | 数据源 | GMRE 接入 |

|---|---|---|---|

| SPR 释放/收储 | > 5000 万桶 | EIA 周度 | Shock: POLICY\_SUPPLY |

| IEA/G7 协调释放 | > 1 亿桶 | IEA 官网 | Shock: POLICY\_SUPPLY + Chain A |

| OPEC+ 减产/增产 | > 100 万桶/日 | OPEC 月报 | Shock: SUPPLY |

| 战略金属储备 | > 全球供应 1% | LME/储备局 | Shock: SUPPLY |

| 天然气储备 | > 100 亿立方米 | IEA/EIA | Shock: SUPPLY |

| 农产品出口禁令 | 全球贸易 > 5% | FAO/USDA | Shock: SUPPLY |



\### 1.2 货币政策类



| 子类 | 触发条件 | 数据源 | GMRE 接入 |

|---|---|---|---|

| 加息/降息 | 单次 > 25bp | 央行官网 | S1 RATES |

| QE/QT 启动或转向 | 月度 > 500 亿美元 | 央行资产负债表 | S4 LIQUIDITY |

| YCC 调整 | 目标区间变动 | BOJ | S1 + Chain B |

| 前瞻指引重大变化 | 点阵图/声明转向 | FOMC | MON\_V2 |

| 紧急流动性工具 | 新设窗口 | Fed/ECB | S5 FUNDING |

| 互换额度 | 新设或扩容 | Fed | S5 + S7 |



\### 1.3 财政政策类



| 子类 | 触发条件 | 数据源 | GMRE 接入 |

|---|---|---|---|

| 财政刺激法案 | > GDP 1% | 财政部 | FIS\_V2 + Chain A |

| 减税/增税 | > GDP 0.5% | 财政部 | FIS\_V2 |

| 债务上限危机 | 政府停摆风险 | 财政部 | S1 + FIS |

| 国债发行计划 | Refunding > 10% | Treasury | FIS\_TERM\_PREMIUM |

| 主权财富基金操作 | > 100 亿美元 | 各国 SWF | S4 |



\### 1.4 外汇/汇率类



| 子类 | 触发条件 | 数据源 | GMRE 接入 |

|---|---|---|---|

| 外汇干预 | > 100 亿美元 | 央行/财务省 | Chain B + RISK |

| 资本管制 | 新增限制 | IMF AREAER | S7 CONTAGION |

| 汇率目标制变动 | 区间调整 | 央行 | Chain B |

| 货币互换 | 新设或扩容 | 央行 | S5 FUNDING |



\### 1.5 金融监管类



| 子类 | 触发条件 | 数据源 | GMRE 接入 |

|---|---|---|---|

| 银行资本要求 | Basel III 变动 | BIS | Fragility |

| 压力测试结果 | 未通过机构 > 1 | Fed/ECB | S6 CREDIT |

| 卖空禁令 | 新增 | SEC/ESMA | RISK |

| 熔断机制 | 触发 | 交易所 | S7 CONTAGION |

| 存款保险扩容 | 上限调整 | FDIC | Fragility |



\### 1.6 地缘政治类



| 子类 | 触发条件 | 数据源 | GMRE 接入 |

|---|---|---|---|

| 制裁 | 涉及主要经济体 | OFAC/EU | Shock: GEOPOLITICAL |

| 出口管制 | 芯片/AI/关键矿产 | BIS/商务部 | Shock: SUPPLY |

| 关税 | 涉及贸易 > 1000 亿 | WTO | Shock: SUPPLY |

| 贸易协议 | 新签或退出 | WTO | Shock: SUPPLY |

| 军事冲突 | 涉及主要产油国 | 新闻 | Shock: GEOPOLITICAL |



\### 1.7 危机应对类



| 子类 | 触发条件 | 数据源 | GMRE 接入 |

|---|---|---|---|

| 系统性救助 | > 1000 亿美元 | 财政部/Fed | Shock: FINANCIAL + S8 |

| 银行接管 | 资产 > 500 亿 | FDIC | S6 + S7 |

| 主权债务重组 | 涉及 > 100 亿 | IMF | S7 CONTAGION |

| 资本注入 | 政府入股 | 新闻 | S6 |



\### 1.8 产业政策类



| 子类 | 触发条件 | 数据源 | GMRE 接入 |

|---|---|---|---|

| 补贴 | > GDP 0.5% | 财政部 | FIS + Shock: POLICY |

| 关税保护 | 涉及行业 > 5% | WTO | Shock: SUPPLY |

| 出口退税 | 税率变动 | 财政部 | Shock: SUPPLY |

| 产业准入 | 新增限制 | 商务部 | Shock: POLICY |



\### 1.9 加密/数字资产类



| 子类 | 触发条件 | 数据源 | GMRE 接入 |

|---|---|---|---|

| 加密监管 | 重大立法 | SEC/MiCA | Shock: POLICY |

| CBDC 启动 | 主要经济体 | 央行 | Shock: POLICY |

| 稳定币监管 | 新规 | 监管机构 | Shock: POLICY |

| 加密禁令 | 主要经济体 | 政府 | Shock: POLICY |



\### 1.10 国际协调类



| 子类 | 触发条件 | 数据源 | GMRE 接入 |

|---|---|---|---|

| G7/G20 联合声明 | 涉及市场 | 官方 | Shock: POLICY |

| IMF 救助 | > 100 亿 SDR | IMF | S7 CONTAGION |

| 世界银行项目 | > 50 亿美元 | WB | Fragility |

| 双边货币协议 | 新签 | 央行 | S5 |



\---



\## 2. 统一数据结构



```python

@dataclass

class PolicyEvent:

&#x20;   # 基本标识

&#x20;   event\_id: str

&#x20;   event\_type: str                  # 10 大类之一

&#x20;   event\_subtype: str               # 细分

&#x20;   event\_date: str                  # YYYY-MM-DD

&#x20;   actor: str                       # Fed/US Treasury/G7/OPEC+/BOJ

&#x20;   target: str                      # 目标（oil/USD/credit）



&#x20;   # 量级评估

&#x20;   scale: float                     # 原始量级

&#x20;   scale\_unit: str                  # 桶/美元/GDP%

&#x20;   scale\_normalized: float          # 归一化（占全球供应%/日需求%/GDP%）



&#x20;   # 时间维度

&#x20;   duration\_days: int               # 预期持续

&#x20;   coverage\_days: int               # 覆盖天数 = scale / daily\_gap

&#x20;   reversibility: float             # 0-1，可逆性



&#x20;   # 可信度

&#x20;   credibility: float               # 0-1（喊话=0.3 / 协调=0.6 / 正式=0.9）

&#x20;   market\_acceptance: float         # 0-1（市场消化度）

&#x20;   backfire\_risk: float             # 0-1（补库反噬等）



&#x20;   # 传导

&#x20;   transmission\_chain: List\[str]    # 传导链

&#x20;   gmre\_shock\_type: str             # 映射到 Shock 7 类

&#x20;   gmre\_s\_states: List\[str]         # 影响哪些 S 状态



&#x20;   # 历史

&#x20;   historical\_precedent: str        # 历史先例

&#x20;   similarity: float                # 相似度



&#x20;   # 元数据

&#x20;   confidence: float

&#x20;   source\_url: str

&#x20;   notes: str

3\. "大额"统一标准

核心逻辑：什么量级的政策事件值得 GMRE 关注？



维度	阈值

单次释放/收储	> 全球需求 0.5%

月度操作	> GDP 0.3%

汇率干预	> 100 亿美元/日

央行资产负债表	> 500 亿美元/月

制裁/关税	涉及贸易 > 1000 亿/年

救助/接管	> 500 亿美元/机构

利率变动	> 25bp

为什么用"占全球需求%"而不是绝对值：能横向对比不同时期的事件。



4\. GMRE 接入点

4.1 Shock 引擎扩展

现有 7 类：FISCAL / LIQUIDITY / POLICY / SUPPLY / FINANCIAL / GEOPOLITICAL / CREDIT



扩展 5 类：



python

POLICY\_SUPPLY        # SPR释放/OPEC+减产

POLICY\_MONETARY      # QE/QT/紧急工具

POLICY\_FISCAL        # 财政刺激/减税

POLICY\_FX            # 汇率干预/资本管制

POLICY\_REGULATORY    # 银行监管/卖空禁令

4.2 Transmission Chain 扩展

现有 3 链：



Chain A: Oil → Inflation → Fed → Rates



Chain B: BOJ → JPY → Carry → Leverage



Chain C: RRP → Buffer → Reserves → Funding



新增 2 链：



Chain D: Policy → Market → Real Economy



示例：G7 抛储 → Oil↓ → Inflation↓ → Fed↓ → Rates↓



Chain E: Policy Event → Expectation → Positioning



示例：口头干预 → 市场预期变化 → 投机头寸调整



4.3 Fragility "政策空间"维度细化

python

PolicySpace = {

&#x20;   "SPR\_remaining": 0.4,        # SPR 余额 / 历史均值

&#x20;   "rate\_cut\_room": 0.3,        # 当前利率 - 中性利率

&#x20;   "fiscal\_room": 0.5,          # 债务/GDP 空间

&#x20;   "fx\_reserves": 0.6,          # 外储充足度

}

4.4 Crisis Fingerprint 扩展

现有指纹：9 个历史危机



新增政策事件指纹：



python

POLICY\_FINGERPRINTS = {

&#x20;   "1973\_OilEmbargo": {...},

&#x20;   "1979\_IranRevolution": {...},

&#x20;   "1985\_PlazaAccord": {...},

&#x20;   "1997\_AsianCrisis\_IMF": {...},

&#x20;   "1998\_LTCM\_Bailout": {...},

&#x20;   "2008\_TARP\_QE": {...},

&#x20;   "2011\_ECB\_LTRO": {...},

&#x20;   "2020\_COVID\_QE": {...},

&#x20;   "2022\_UK\_LDI": {...},

&#x20;   "2023\_SVB\_Rescue": {...},

&#x20;   "2026\_G7\_SPR": {...},  # 本次新增

}

5\. 历史案例库（部分）

货币政策类

事件	日期	量级	GMRE 映射

Fed QE1	2008-11	1.75 万亿	S4 解除

Fed QE2	2010-11	6000 亿	S4 解除

Fed QE3	2012-09	85 亿/月	S4 解除

ECB LTRO	2011-12	1 万亿欧元	S5 解除

Fed QE4（无限）	2020-03	无限	S4+S8

BOJ YCC	2016-09	10Y≈0%	Chain B 激活

Fed 加息周期	2022-03	+525bp	S1 持续

能源/大宗商品类

事件	日期	量级	GMRE 映射

1973 石油禁运	1973-10	500 万桶/日	S2 滞胀

1979 伊朗革命	1979-01	400 万桶/日	S2 滞胀

1990 海湾战争	1990-08	430 万桶/日	S2 短期

2014 OPEC+增产	2014-11	不限产	S2 解除

2020 OPEC+减产	2020-04	970 万桶/日	S2 短期

2022 俄乌冲突	2022-02	制裁	S2 + S7

2026 G7 抛储	2026-10	1 亿桶	S2 短暂解除

危机应对类

事件	日期	量级	GMRE 映射

1998 LTCM	1998-09	36 亿	S7 短期

2008 TARP	2008-10	7000 亿	S8

2008 AIG	2008-09	850 亿	S7

2011 欧债	2011-07	ECB 干预	S7 短期

2022 UK LDI	2022-09	BOE 紧急购债	S7 短期

2023 SVB	2023-03	BTFP 设立	S5 + S6

2023 瑞信	2023-03	UBS 收购	S6 + S7

地缘政治类

事件	日期	量级	GMRE 映射

2018 中美贸易战	2018-03	关税 3600 亿	Shock: SUPPLY

2022 芯片出口管制	2022-10	全面限制	Shock: SUPPLY

2022 俄制裁	2022-02	全面	S2 + S7

6\. 实施路线图（10-21 后）

阶段 1（GMRE 3.4）：核心事件类型 + 数据结构

时间：2026-10-21 → 2026-11-21（4 周）



定义 10 大类 + 子类



统一数据结构 PolicyEvent



手动录入 2020-2026 历史事件（约 100 条）



接入 GMRE Shock 引擎



阶段 2（GMRE 3.5）：历史案例库 + 指纹匹配

时间：2026-11-21 → 2026-12-19（4 周）



录入 1970-2020 历史事件（约 200 条）



建立事件指纹库



与 Crisis Fingerprint 联动



阶段 3（GMRE 3.6）：自动抓取 + 实时监控

时间：2026-12-19 → 2027-02-13（8 周）



自动抓取 EIA SPR / OPEC 月报 / Fed 声明 / Treasury 发债 / OFAC 名单



事件自动识别



实时报告到飞书



7\. Pending 清单

text

2026-10-04  P1  PET设计草案          Policy\_Event\_Tracker\_10类      10-21后

2026-10-04  P1  SPR数据接入          EIA周度SPR余额                 阶段3

2026-10-04  P1  OPEC数据接入         月度产量决策                    阶段3

2026-10-04  P1  央行政策声明抓取      Fed/ECB/BOJ                   阶段3 NLP

2026-10-04  P2  历史事件库           1970-2026约300条               阶段1+2

2026-10-04  P2  事件指纹             与Crisis Fingerprint联动       阶段2

2026-10-04  P2  大额触发条件         占全球需求0.5%统一标准          阶段1

8\. 关键洞察

政策事件是"外生冲击"的主要来源



GMRE 现有 Shock 引擎能捕捉"强度"，但缺"事件类型"和"量级评估"



PET 补上这块



GMRE 升级路径



现状：状态识别（R/S/F）



未来：状态识别 + 事件驱动双引擎



PET 的四个核心概念



一次性供给 → coverage\_days（覆盖天数）



预期管理 → credibility（可信度）



市场质疑 → market\_acceptance（市场消化度）



补库反噬 → backfire\_risk（反噬风险）



与其他模块的关系



Shock 引擎：扩展 5 类



Transmission：新增 Chain D/E



Fragility：政策空间维度细化



Crisis Fingerprint：新增政策事件指纹



9\. 参考事件：2026-10-04 G7 抛储

事件：法国总统马克龙 10-02 召集 G7 视频会议，通过 IEA 协调释放最多 1 亿桶 SPR，持续 4 个月，前 20 天集中投柴油。



触发：柴油价格创新高，全球柴油供给缺口约 150 万桶/日。



市场反应：纽约原油跌 1.9%，金价跌 1%，欧美股市涨，德债收益率降至三周低位。



GMRE 分析（示例）：



json

{

&#x20; "event\_type": "ENERGY",

&#x20; "event\_subtype": "SPR\_RELEASE",

&#x20; "event\_date": "2026-10-04",

&#x20; "actor": "G7/IEA",

&#x20; "scale": 100000000,

&#x20; "scale\_unit": "barrels",

&#x20; "coverage\_days": 66,

&#x20; "credibility": 0.6,

&#x20; "market\_acceptance": 0.3,

&#x20; "backfire\_risk": 0.5,

&#x20; "gmre\_shock\_type": "POLICY\_SUPPLY",

&#x20; "gmre\_s\_states": \["S2"],

&#x20; "historical\_precedent": "1990\_GulfWar\_SPR",

&#x20; "similarity": 0.4

}

关键提示：抛储是"一次性供给"，治标不治本；市场质疑（油价反弹）是重要信号；补库反噬是未来隐患。



草案结束



下一步：10-21 后作为 GMRE 3.4 的设计输入，分三阶段实施。



text



\## 第三步：保存并验证



Ctrl+S 保存。然后：



```cmd

dir D:\\HGZC\\docs\\GMRE\_3.4\_PET\_draft.md

应该看到一个几 KB 的文件。



第四步：同步到飞书文档

把这份草案追加到《GMRE 项目主页》的"待设计模块"章节，或在飞书新建一个《GMRE 3.4 PET 设计草案》文档。



第五步：更新决策日志

在《GMRE 决策日志》追加一条：



markdown

\## 2026-10-04



\### 决策 17：启动 Policy Event Tracker 设计

\*\*内容\*\*：基于 G7 抛储事件，系统化设计政策事件追踪模块。

\*\*范围\*\*：10 大类政策事件 + 统一数据结构 + 历史案例库。

\*\*决策\*\*：作为 GMRE 3.4 的设计输入，10-21 后分三阶段实施。

\*\*关联文件\*\*：`D:\\HGZC\\docs\\GMRE\_3.4\_PET\_draft.md`

\*\*实施时间\*\*：

\- 阶段 1（GMRE 3.4）：10-21 → 11-21

\- 阶段 2（GMRE 3.5）：11-21 → 12-19

\- 阶段 3（GMRE 3.6）：12-19 → 2027-02-13

