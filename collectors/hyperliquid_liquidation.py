"""
Hyperliquid 链上真实清算事件（WebSocket liquidationFills）
无 IP 封锁，Actions 可直连
输出: data/hyperliquid_liquidation.csv（累积）
"""
import asyncio
import json
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

try:
    import websockets
except ImportError:
    print("[error] pip install websockets")
    raise

OUT = Path(__file__).parent.parent / "data" / "hyperliquid_liquidation.csv"
WS_URL = "wss://api.hyperliquid.xyz/ws"
TARGET_COINS = {"BTC", "ETH", "SOL"}


async def keepalive(ws):
    while True:
        try:
            await asyncio.sleep(30)
            await ws.send(json.dumps({"method": "ping"}))
        except Exception:
            return


async def collect(duration):
    events = []
    t_start = asyncio.get_event_loop().time()

    try:
        async with websockets.connect(WS_URL, ping_interval=None) as ws:
            await ws.send(json.dumps({
                "method": "subscribe",
                "subscription": {"type": "liquidationFills"}
            }))
            print("[ok] connected + subscribed")

            ping_task = asyncio.create_task(keepalive(ws))

            try:
                while asyncio.get_event_loop().time() - t_start < duration:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                        data = json.loads(msg)
                        if data.get("channel") == "liquidationFills":
                            for ev in data.get("data", []):
                                coin = ev.get("coin")
                                if coin not in TARGET_COINS:
                                    continue
                                px = float(ev.get("px", 0))
                                sz = float(ev.get("sz", 0))
                                events.append({
                                    "datetime": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                                    "coin": coin,
                                    "side": ev.get("side"),  # 'A' = ask (long liq), 'B' = bid (short liq)
                                    "price": px,
                                    "size": sz,
                                    "notional_usd": px * sz,
                                })
                                print(f"[liq] {coin:5s} {ev.get('side'):3s} ${px*sz:>12,.2f} @ {px}")
                    except asyncio.TimeoutError:
                        elapsed = int(asyncio.get_event_loop().time() - t_start)
                        print(f"[{elapsed:3d}s] (no event)")
                        continue
            finally:
                ping_task.cancel()
    except Exception as e:
        print(f"[error] {e}")

    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=90)
    args = parser.parse_args()

    print(f"[start] 采集 {args.duration}s")
    events = asyncio.run(collect(args.duration))

    if not events:
        print("[note] 采集期间无清算事件")
        return

    df_new = pd.DataFrame(events)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['datetime', 'coin', 'side', 'price', 'size'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values('datetime')
    df.to_csv(OUT, index=False)
    print(f"[saved] {OUT} ({len(df)} 总行 / 本次 +{len(events)})")
    print(f"[summary] 本次总额 ${df_new['notional_usd'].sum():,.2f}")
    for coin in df_new['coin'].unique():
        sub = df_new[df_new['coin'] == coin]
        print(f"  {coin}: {len(sub)} 事件, ${sub['notional_usd'].sum():,.2f}")


if __name__ == "__main__":
    main()