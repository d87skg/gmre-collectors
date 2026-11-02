\# GMRE 4.0 Master Plan



\## 版本目标



从 GMRE 3.3（美国中心宏观状态机）升级到 GMRE 4.0（中美双轨 + 四资产联动 + 流动性微观 + 双阶段操作）。



\## 五大新增能力



\### 1. 美元锚定决策树

\- DXY 5y 分位 + 四资产联动

\- 输出"降息倒逼 vs 高利率维持"路径



\### 2. CALI 流动性温度计

\- MOVE + VIX + HY-OAS + 期限溢价

\- 0-100 评分，70+ 触发最大保护



\### 3. 拥挤度引擎

\- CFTC COT + BTC FR + PCR + ETF 成交

\- 捕捉"宏观方向对但被踩踏清算"的风险



\### 4. 中美双轨

\- A 股政策底 / 市场底分离判定

\- 只有全球共振才联动



\### 5. 双阶段操作

\- 上半场（去杠杆）：现金 50-70%

\- 过渡期：现金 40-60%

\- 下半场（降息重估）：现金 10-20%



\## 新增压力层



\- \*\*S9 美债流动性危机\*\*：30Y-10Y>50bp + MOVE>120

\- \*\*S10 美元信用降级\*\*：DXY 5y<10% + Gold 5y>80% + 10Y 5y>90%



\## 新增传导链



\- \*\*Chain D\*\*：AI 信贷 → NDX → 税收 → 财政 → 期限溢价

\- \*\*Chain E\*\*：美元 → 石油 → 黄金 → 美债



\## 关键纪律



1\. \*\*绝不把历史样本当作规则编码\*\*（只作报告文本）

2\. \*\*绝不把"美联储降息"作为 A 股看多信号\*\*

3\. \*\*政策底 ≠ 市场底\*\*（滞后 1-3 月，二次探底常态）

4\. \*\*只有全球共振（HY OAS>500 + 5D 相关>0.5）才中美同步\*\*



\## 落地清单（已完成）



| 类型 | 文件 | 状态 |

| :--- | :--- | :---: |

| 新建 | `dollar\_anchor.py` | ✅ |

| 新建 | `cali\_engine.py` | ✅ |

| 新建 | `crowding\_engine.py` | ✅ |

| 新建 | `a\_share\_policy\_engine.py` | ✅ |

| 新建 | `a\_share\_market\_engine.py` | ✅ |

| 新建 | `china\_us\_linkage\_engine.py` | ✅ |

| 新建 | `collectors/move\_index.py` | ✅ |

| 新建 | `collectors/etf\_flow.py` | ✅ |

| 新建 | `collectors/fomc\_text.py` | ✅ |

| 修改 | `data\_correction.py` | ✅ |

| 修改 | `stress\_overlay\_v2.py` | ✅ |

| 修改 | `transmission\_graph.py` | ✅ |

| 修改 | `lti\_engine.py` | ✅ |

| 修改 | `run\_v4.py` | ✅ |

| 修改 | `send\_local\_feishu.py` | ✅ |

| 修改 | `daily\_intelligence.py` | ✅ |



\## 后续（Brier 后）



\- FOMC NLP 鹰鸽打分

\- 13F 机构持仓

\- Petrodollar 引擎

\- 期权凸性对冲矩阵

