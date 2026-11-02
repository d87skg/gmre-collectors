# -*- coding: utf-8 -*-
"""
补丁 05: collectors/market.py
  - 顶部加 sys.path 兜底 (兼容 python xx.py 和 python -m collectors.market)
  - 末尾加 __main__ 入口: fetch + upsert_many
"""
import re
import shutil
from pathlib import Path

TARGET = Path(r"D:\HGZC\collectors\market.py")
BACKUP = TARGET.with_suffix(".py.bak2")

shutil.copy2(TARGET, BACKUP)
print("[OK] backup ->", BACKUP)

raw = TARGET.read_text(encoding="utf-8")

# --- 1) 顶部 sys.path 兜底 ---
if "_PROJECT_ROOT = _Path(__file__).resolve().parents[1]" not in raw:
    m = re.search(r"^(\s*(?:import|from)\s+\S+)", raw, flags=re.MULTILINE)
    if not m:
        raise RuntimeError("找不到 import 段")
    bootstrap = (
        "import sys as _sys\n"
        "from pathlib import Path as _Path\n"
        "_PROJECT_ROOT = _Path(__file__).resolve().parents[1]\n"
        "if str(_PROJECT_ROOT) not in _sys.path:\n"
        "    _sys.path.insert(0, str(_PROJECT_ROOT))\n"
    )
    raw = raw[:m.start()] + bootstrap + raw[m.start():]
    print("[OK] inserted sys.path bootstrap")
else:
    print("[SKIP] sys.path bootstrap already present")

# --- 2) 末尾加 __main__ 入口 ---
if 'if __name__ == "__main__":' in raw:
    print("[SKIP] __main__ entry already present")
else:
    entry = (
        "\n\n"
        "# ============ 可执行入口 (v1.0) ============\n"
        'if __name__ == "__main__":\n'
        "    import logging\n"
        "    from collections import Counter\n"
        "\n"
        "    logging.basicConfig(\n"
        "        level=logging.INFO,\n"
        '        format="%(asctime)s %(levelname)s %(name)s: %(message)s",\n'
        "    )\n"
        "\n"
        "    from core.database import Database\n"
        "\n"
        '    logger.info("[market] starting collection...")\n'
        "    collector = MarketCollector(env=MarketCollector._env_from_dotenv())\n"
        "    observations = collector._safe_fetch()\n"
        "\n"
        "    if not observations:\n"
        '        logger.warning("[market] no observations fetched")\n'
        "        _sys.exit(1)\n"
        "\n"
        '    db = Database("data/macro.db")\n'
        "    n = db.upsert_many(observations)\n"
        '    logger.info("[market] saved %d observations", n)\n'
        "\n"
        "    cnt = Counter(o.series_id for o in observations)\n"
        "    for sid, c in sorted(cnt.items()):\n"
        '        logger.info("[market]   %s: %d", sid, c)\n'
        "\n"
        "    _sys.exit(0)\n"
    )
    raw = raw.rstrip() + entry
    print("[OK] appended __main__ entry")

TARGET.write_text(raw, encoding="utf-8")
print("[OK] written ->", TARGET)