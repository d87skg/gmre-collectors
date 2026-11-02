# -*- coding: utf-8 -*-
"""
export_deps_for_doubao.py
打包豆包缺失的 3 个依赖，排除 .bak / __pycache__ / .pyc。
"""
import zipfile
import hashlib
from pathlib import Path
from datetime import datetime

BASE = Path(r"D:\HGZC")
EXPORT_DIR = BASE / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
ZIP_PATH = EXPORT_DIR / f"gmre_deps_export_{TS}.zip"

INCLUDE = [
    "engines_v2",
    "tools/rrp_guard.py",
    "core/validator.py",
]

EXCLUDE = ["__pycache__", ".pyc", ".pyo", ".bak", ".log", ".zip"]

def skip(p: Path):
    return any(x in str(p) for x in EXCLUDE)

manifest = [f"GMRE Deps Export {datetime.now().isoformat(timespec='seconds')}"]
missing, packed = [], []

with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
    for rel in INCLUDE:
        src = BASE / rel
        if not src.exists():
            missing.append(rel)
            continue
        if src.is_dir():
            for f in src.rglob("*"):
                if f.is_file() and not skip(f):
                    arc = f.relative_to(BASE)
                    zf.write(f, arc)
                    packed.append(str(arc))
        else:
            if not skip(src):
                arc = src.relative_to(BASE)
                zf.write(src, arc)
                packed.append(str(arc))

manifest.append(f"Packed: {len(packed)}")
manifest.append(f"Missing: {len(missing)}")
manifest.append("=== Packed ===")
manifest.extend(packed)
manifest.append("=== Missing ===")
manifest.extend(missing)

manifest_path = EXPORT_DIR / f"deps_manifest_{TS}.txt"
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