@echo off
chcp 65001 >nul
:: 🆕 修改为当前脚本所在目录，保证在沙盒和生产都能正确运行
cd /d %~dp0

:: 自动创建 logs 文件夹（如果不存在）
if not exist "logs" mkdir "logs"

:: 获取当前日期并生成日志文件名
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set datestr=%%c-%%a-%%b
set logfile=logs\pipeline_%datestr%.log

:: 将后续所有输出重定向到屏幕和日志文件
echo ======================================================== >> %logfile%
echo   Run at %time% >> %logfile%
echo ======================================================== >> %logfile%

echo ========================================================
echo   GMRE 4.1 Daily Pipeline
echo ========================================================

echo [1/16] Data correction (FRED/WTI/GOLD)...
.venv\Scripts\python.exe -X utf8 engines_v3\data_correction.py
if %errorlevel% neq 0 (
    echo FATAL: data correction failed, pipeline aborted!
    exit /b 1
)

echo [1.5/16] Realtime market data (SP500/VIX override)...
.venv\Scripts\python.exe -X utf8 collectors\realtime_market.py

echo [2/16] Enhanced liquidity data...
if exist collectors\enhanced_data.py (.venv\Scripts\python.exe -X utf8 collectors\enhanced_data.py)

echo [2.5/16] Global data sanitizer...
.venv\Scripts\python.exe -X utf8 tools\data_sanitizer.py
if %errorlevel% neq 0 (
    echo FATAL: data sanitizer failed, pipeline aborted!
    exit /b 1
)

echo [3/16] Smart gap check for market history...
.venv\Scripts\python.exe -X utf8 tools\check_and_backfill.py

echo [4/16] Sync feishu snapshot [DISABLED - V4.1 Proxy Layer]...
:: 🚨 核心重构：彻底切断飞书文本反解析覆写
:: .venv\Scripts\python.exe -X utf8 tools\sync_feishu_snapshot.py
:: .venv\Scripts\python.exe -X utf8 tools\apply_feishu_override.py

echo [5/16] Compute percentiles...
.venv\Scripts\python.exe -X utf8 tools\compute_percentile.py
if %errorlevel% neq 0 (
    echo FATAL: percentile computation failed, pipeline aborted!
    exit /b 1
)

echo [6/16] Contagion engine...
.venv\Scripts\python.exe -X utf8 engines_v3\contagion_engine.py

echo [7/16] CAPS commodity collection...
if exist collectors\caps_collector.py (.venv\Scripts\python.exe -X utf8 collectors\caps_collector.py)
if exist tools\sync_commodity_github.py (.venv\Scripts\python.exe -X utf8 tools\sync_commodity_github.py)

echo [8/16] LTI engine...
if exist engines_v3\lti_engine.py (.venv\Scripts\python.exe -X utf8 engines_v3\lti_engine.py)

:: 🆕 新增微结构数据采集
echo [8.1/16] Deribit skew collection...
if exist collectors\deribit_skew.py (.venv\Scripts\python.exe -X utf8 collectors\deribit_skew.py)

echo [8.2/16] Hyperliquid depth collection...
if exist collectors\hyperliquid_depth.py (.venv\Scripts\python.exe -X utf8 collectors\hyperliquid_depth.py)

echo [8.3/16] Extra macro (Gas/Rebar/VXV)...
.venv\Scripts\python.exe -X utf8 collectors\extra_macro.py

echo [8.5/16] Copper spread engine...
.venv\Scripts\python.exe -X utf8 engines_v3\spread_engine.py

echo [9/16] GMRE V4 main engine...
.venv\Scripts\python.exe -X utf8 engines_v3\run_v4.py
:: 🆕 注意：如果 run_v4 触发 P0 阻断，这里会报 FATAL 并直接中断流水线，绝不推送假报告
if %errorlevel% neq 0 (
    echo FATAL: main engine failed or P0 blocked!
    exit /b 1
)

echo [10/16] Daily report...
if exist engines_v3\generate_report.py (.venv\Scripts\python.exe -X utf8 engines_v3\generate_report.py)

echo [11/16] Brier calibration...
if exist engines_v3\calibration_tracker.py (.venv\Scripts\python.exe -X utf8 engines_v3\calibration_tracker.py)

echo [12/16] Data freshness check...
.venv\Scripts\python.exe -X utf8 tools\check_freshness.py

echo [13/16] Push to Feishu...
.venv\Scripts\python.exe -X utf8 tools\send_local_feishu.py

echo ========================================================
echo   Pipeline completed successfully
echo ========================================================
echo ======================================================== >> %logfile%
echo   Pipeline completed >> %logfile%
exit /b 0