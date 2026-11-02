\# GMRE 4.0 快速开始



\## 首次运行前的检查



1\. 确认 `.env` 文件存在，包含 `FRED\_API\_KEY` / `FEISHU\_WEBHOOK` / `FEISHU\_SECRET`

2\. 确认 `data/macro.db` 存在

3\. 虚拟环境已安装所有依赖：`.venv\\Scripts\\python.exe -m pip install pandas numpy requests scikit-learn scipy statsmodels python-dotenv yfinance pyyaml`



\## 首次运行



```cmd

cd /d D:\\HGZC

.venv\\Scripts\\python.exe auto\_daily.bat

