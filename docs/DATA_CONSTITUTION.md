\# GMRE DATA CONSTITUTION



\## 1. 数据必须携带元信息

series\_id, observation\_date, value, published\_at, vintage\_date,

retrieved\_at, source, frequency, unit, revision, pit\_status, quality\_score



\## 2. PIT 状态分级

\- VERIFIED\_PIT：权威源，含 publication 时间

\- PARTIAL\_PIT：估算时间

\- ESTIMATED\_PIT：推算

\- REALTIME：实时市场数据

\- MARKET：市场收盘

\- ALTERNATIVE：另类数据



\## 3. 回测模式

\- STRICT BACKTEST：只用 VERIFIED\_PIT

\- RESEARCH BACKTEST：VERIFIED + PARTIAL

\- LIVE：全部允许



\## 4. 质量分不改变经济意义

质量分只影响 confidence，不改变 score 本身。



\## 5. 历史真值必须保留

1980年利率15%+、2020年负油价、1971年USDJPY 357 都是真实历史，

不能以"异常"为理由删除。

