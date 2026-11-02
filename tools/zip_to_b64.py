# -*- coding: utf-8 -*-
"""
zip_to_b64.py
用途：把 zip 转成 base64 文本，分段输出，便于贴到聊天工具。
"""
import base64
from pathlib import Path

ZIP = Path(r"D:\HGZC\exports\gmre_core_export_20261003_221221.zip")
OUT = Path(r"D:\HGZC\exports\gmre_core_export_b64.txt")

data = ZIP.read_bytes()
b64 = base64.b64encode(data).decode("ascii")

SEG_SIZE = 2500
segments = [b64[i:i+SEG_SIZE] for i in range(0, len(b64), SEG_SIZE)]

lines = []
lines.append("# GMRE Core Export - Base64 Encoded")
lines.append(f"# zip 原文件: {ZIP.name}")
lines.append(f"# zip 大小: {len(data)} bytes")
lines.append(f"# base64 长度: {len(b64)} 字符")
lines.append(f"# 分段数: {len(segments)}")
lines.append(f"# 每段: {SEG_SIZE} 字符")
lines.append("#")
lines.append("# 使用说明：")
lines.append("#   1. 按顺序复制每个 ---SEG-xx--- 到下一个 ---SEG-xx--- 之间的内容")
lines.append("#   2. 去掉段标题和换行，得到连续 base64 字符串")
lines.append("#   3. base64 decode 得到原始 zip")
lines.append("#")
for i, seg in enumerate(segments, 1):
    lines.append(f"---SEG-{i:02d}-of-{len(segments):02d}---")
    lines.append(seg)
    lines.append("")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"[ok] {OUT}")
print(f"[size] {OUT.stat().st_size} bytes")
print(f"[segments] {len(segments)}")
print(f"[seg_chars] {SEG_SIZE}")