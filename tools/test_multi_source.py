# -*- coding: utf-8 -*-
"""tools/test_multi_source.py - 验证多源自动降级"""
import sys, os, sqlite3
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_proxy import load
from core.errors import DataStaleError, DataMissingError

DB_PATH = 'data/macro.db'


def test(series_id):
    print(f"\n{'='*60}")
    print(f"  测试 series_id = {series_id}")
    print(f"{'='*60}")
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            s = load(conn, series_id, limit=5, verbose=True, strict_fresh=False)
        finally:
            conn.close()

        if s is None or s.empty:
            print(f"  ❌ 无数据")
            return

        lineage = s.attrs.get('lineage', {})
        print(f"  📊 实际使用源    : {lineage.get('used_id')}")
        print(f"  📅 最新观测日    : {lineage.get('last_obs_date')}")
        print(f"  ⏱️ 滞后天数      : {lineage.get('days_lag')}")
        print(f"  🎯 SLA 上限      : {lineage.get('sla_days')}")
        print(f"  🚦 状态          : {'STALE' if lineage.get('stale') else 'OK'}")

        if lineage.get('used_id') != lineage.get('requested'):
            print(f"  🔀 已发生降级：{lineage.get('requested')} -> {lineage.get('used_id')}")
        else:
            print(f"  ✅ 使用主源")

        # 检查是否有备源数据
        try:
            conn = sqlite3.connect(DB_PATH)
            from core import units
            cands = units.candidates_of(series_id)
            available_sources = []
            for c in cands:
                row = conn.execute(
                    "SELECT MAX(obs_date) FROM observations WHERE series_id=?", (c,)
                ).fetchone()
                if row and row[0]:
                    available_sources.append(f"{c} (latest={row[0]})")
            conn.close()
            if len(available_sources) > 1:
                print(f"  🗂️ 备源池        : {available_sources}")
            else:
                print(f"  🗂️ 备源池        : 仅主源，无备用")
        except Exception:
            pass

    except DataStaleError as e:
        print(f"  ⚠️ 主源数据陈旧: {e}")
        print(f"  ℹ️  建议检查备源采集器是否已成功运行（CoinGecko/BIS/TwelveData）")
    except DataMissingError as e:
        print(f"  ❌ 完全没有数据: {e}")
    except Exception as e:
        print(f"  ❌ 异常: {e}")


if __name__ == "__main__":
    for sid in [
        'FEDFUNDS',
        'DXY_PROXY',
        'BTC_SPOT_PRICE_1H',
        'WTI_OIL',
        'GOLD_PRICE',
    ]:
        test(sid)
    print(f"\n{'='*60}\n  测试完成\n{'='*60}")