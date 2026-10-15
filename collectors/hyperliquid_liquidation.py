# -*- coding: utf-8 -*-
"""hyperliquid_liquidation.py - Hyperliquid 链上清算流（含主动心跳）"""
import asyncio
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

try:
    import websockets
except ImportError:
    print("[error] pip install websockets")
    raise

DATA_DIR = Path(__file__).parent.parent / "data" / "lti"
DATA_DIR.mkdir(parents=True, exist_ok=True)
WS_URL = "wss://api.hyperliquid.xyz/ws"


async def keepalive(ws):
    """每 30 秒发一次 ping 保持连接"""
    while True:
        try:
            await asyncio.sleep(30)
            await ws.send(json.dumps({"method": "ping"}))
        except Exception:
            return


async def collect_once(duration, events, t_start):
    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        # 订阅
        await ws.send(json.dumps({
            "method": "subscribe",
            "subscription": {"type": "liquidationFills"}
        }))
        print(f"[ok] 已连接并订阅")

        # 启动心跳
        ping_task = asyncio.create_task(keepalive(ws))

        try:
            while asyncio.get_event_loop().time() - t_start < duration:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(msg)
                    if data.get("channel") == "liquidationFills":
                        for event in data.get("data", []):
                            row = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "coin": event.get("coin"),
                                "side": event.get("side"),
                                "price": event.get("px"),
                                "size": event.get("sz"),
                                "notional_usd": float(event.get("px", 0)) * float(event.get("sz", 0)),
                                "user": event.get("user"),
                                "source": "hyperliquid_liquidationFills",
                                "data_type": "observed",
                            }
                            events.append(row)
                            print(f"[liq] {row['coin']:6s} {row['side']:6s} "
                                  f"${row['notional_usd']:>12,.2f} @ {row['price']}")
                except asyncio.TimeoutError:
                    elapsed = int(asyncio.get_event_loop().time() - t_start)
                    print(f"[{elapsed:3d}s] (心跳)")
                    continue
                except websockets.exceptions.ConnectionClosed:
                    print(f"[reconnect] 连接断开")
                    return False
        finally:
            ping_task.cancel()

    return True


async def subscribe(duration):
    events = []
    t_start = asyncio.get_event_loop().time()
    retry_count = 0

    print(f"[start] 目标采集 {duration}s")
    print("-" * 60)

    while asyncio.get_event_loop().time() - t_start < duration:
        try:
            if await collect_once(duration, events, t_start):
                break
        except Exception as e:
            print(f"[error] {e}")
        retry_count += 1
        if retry_count > 20:
            break
        await asyncio.sleep(2)

    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()

    events = asyncio.run(subscribe(args.duration))

    print(f"\n{'='*60}")
    if events:
        import pandas as pd
        df = pd.DataFrame(events)
        out = DATA_DIR / "hyperliquid_liquidation.csv"
        df.to_csv(out, index=False)
        print(f"[saved] {out} ({len(events)} events)")
        print(f"[summary] 总清算额: ${df['notional_usd'].sum():,.2f}")
        for coin in df['coin'].unique():
            sub = df[df['coin'] == coin]
            print(f"  {coin}: {len(sub)} 事件, ${sub['notional_usd'].sum():,.2f}")
    else:
        print(f"[note] 采集期间无清算事件")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()