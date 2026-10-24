"""Point-in-Time availability policy.
Existing v1.1 rows do not contain historical publication/vintage timestamps, so
legacy rows are explicitly marked ESTIMATED rather than pretending they are strict PIT.
"""
from datetime import datetime,timedelta

# Conservative legacy availability lags. Replace with source-provided vintage/publish times
# when the collectors are upgraded.
LAGS={
 'VIX':timedelta(days=1),'YC2Y':timedelta(days=1),'YC5Y':timedelta(days=1),'YC10Y':timedelta(days=1),'YC30Y':timedelta(days=1),
 'DXY_PROXY':timedelta(days=1),'ECB_EURUSD':timedelta(days=1),'GOLD_PRICE':timedelta(hours=1),
 'TGA_NET_FLOW':timedelta(days=1),'DEBT_TOTAL':timedelta(days=1),
 'WB_GDP_GROWTH':timedelta(days=30),'WB_INFLATION':timedelta(days=30),
 'BTC_PRICE':timedelta(0),'ETH_PRICE':timedelta(0),'SOL_PRICE':timedelta(0),
 'BTC_24H':timedelta(0),'BTC_7D':timedelta(0),'ETH_24H':timedelta(0),'ETH_7D':timedelta(0),
 'LLAMA_TVL_TOTAL':timedelta(0),'LLAMA_STABLECOINS':timedelta(0),'LLAMA_DEX_VOL':timedelta(0),
}

def estimated_available_at(series_id,timestamp):
    lag=LAGS.get(series_id,timedelta(days=1))
    return timestamp+lag
