# -*- coding: utf-8 -*-
"""
export_gmre_for_doubao.py
用途：打包 GMRE 核心模块，用于上传给豆包云电脑移植。
纪律：只读源码，不改任何文件。
"""
import zipfile
import hashlib
from pathlib import Path
from datetime import datetime

BASE = Path(r"D:\HGZC")
EXPORT_DIR = BASE / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
ZIP_PATH = EXPORT_DIR / f"gmre_core_export_{TS}.zip"

INCLUDE = [
    "engines_v3/run_v4.py",
    "engines_v3/defense_v4.py",
    "engines_v3/stress_overlay_v2.py",
    "engines_v3/fragility_engine.py",
    "engines_v3/shock_engine.py",
    "engines_v3/transmission_graph.py",
    "engines_v3/crisis_fingerprint.py",
    "engines_v3/scenario_tree.py",
    "engines_v3/engine_mon_v2.py",
    "engines_v3/engine_fis_v2.py",
    "engines_v3/engine_inf_expect.py",
    "engines_v3/data_correction.py",
    "engines_v3/probability_engine.py",
    "engines_v3/invalidation_conditions.py",
    "core/schema.py",
    "core/database.py",
    "core/normalizer.py",
    "core/pit.py",
    "core/config.py",
    "config.yaml",
]

EXCLUDE_PATTERNS = ["__pycache__", ".pyc", ".pyo", ".db", ".log", ".zip", ".bak"]

def should_exclude(p: Path) -> bool:
    s = str(p)
    return any(pat in s for pat in EXCLUDE_PATTERNS)

manifest = []
manifest.append("GMRE Core Export Manifest")
manifest.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
manifest.append(f"Base: {BASE}")
manifest.append("")

missing, packed = [], []

with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
    for rel in INCLUDE:
        src = BASE / rel
        if not src.exists():
            missing.append(rel)
            continue
        if src.is_dir():
            for f in src.rglob("*"):
                if f.is_file() and not should_exclude(f):
                    arc = f.relative_to(BASE)
                    zf.write(f, arc)
                    packed.append(str(arc))
        else:
            if not should_exclude(src):
                arc = src.relative_to(BASE)
                zf.write(src, arc)
                packed.append(str(arc))

manifest.append(f"Packed: {len(packed)}")
manifest.append(f"Missing: {len(missing)}")
manifest.append("")
manifest.append("=== Packed ===")
manifest.extend(packed)
manifest.append("")
manifest.append("=== Missing ===")
manifest.extend(missing)

manifest_path = EXPORT_DIR / f"manifest_{TS}.txt"
manifest_path.write_text("\n".join(manifest), encoding="utf-8")

h = hashlib.sha256()
with ZIP_PATH.open("rb") as f:
    for chunk in iter(lambda: f.read(8192), b""):
        h.update(chunk)

print(f"[zip] {ZIP_PATH}")
print(f"[size] {ZIP_PATH.stat().st_size / 1024:.1f} KB")
print(f"[sha256] {h.hexdigest()}")
print(f"[manifest] {manifest_path}")
print(f"[packed] {len(packed)} files")
if missing:
    print(f"[missing] {len(missing)}:")
    for m in missing:
        print(f"  - {m}")