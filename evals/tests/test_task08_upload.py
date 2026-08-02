#!/usr/bin/env python3
"""CDD-тест задачи #8 — Video Upload (S3 + ffprobe)."""
from __future__ import annotations
import os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
S3_PATH = REPO / "apps" / "web" / "lib" / "server" / "s3.ts"
PRESIGN_PATH = REPO / "apps" / "web" / "app" / "api" / "upload" / "presign" / "route.ts"
COMPLETE_PATH = REPO / "apps" / "web" / "app" / "api" / "upload" / "complete" / "route.ts"

results = []
def check(n, ok, d=""): results.append((n, "OK" if ok else "FAIL", d)); print(f"  {'OK  ' if ok else 'FAIL'}  {n}" + (f"  →  {d}" if d else ""))
def skip(n, r): results.append((n, "SKIP", r)); print(f"  SKIP  {n}  →  {r}")

print("== Статический уровень ==")
s3 = S3_PATH.read_text("utf-8") if S3_PATH.exists() else ""
check("S3 модуль существует", S3_PATH.exists())
check("presigned URL generation", "presign" in s3.lower() or "getSignedUrl" in s3 or "createPresignedPost" in s3)
check("API presign route существует", PRESIGN_PATH.exists())
check("API complete route существует", COMPLETE_PATH.exists())

presign = PRESIGN_PATH.read_text("utf-8") if PRESIGN_PATH.exists() else ""
complete = COMPLETE_PATH.read_text("utf-8") if COMPLETE_PATH.exists() else ""
s3_all = s3 + presign + complete
check("ограничение 700MB", "700" in s3_all)
check("типы файлов (mp4/mov/avi)", any(x in s3_all for x in ["mp4", "mov", "avi", "ALLOWED_CODECS"]))
check("ffprobe валидация", "ffprobe" in s3_all.lower())
check("tenant_id в S3 ключе", "tenant" in s3_all.lower())

print("\n== Поведенческий уровень ==")
if not os.environ.get("BASE_URL"):
    for i in range(8, 12): skip(f"кейс {i}", "нет BASE_URL")
else:
    skip("presigned upload", "требует S3+живой сервер")
    skip("ffprobe валидация", "требует S3+живой сервер")

n_pass = sum(1 for _,s,_ in results if s=="OK"); n_fail = sum(1 for _,s,_ in results if s=="FAIL")
print(f"\n{'GREEN' if not n_fail else 'RED'} — pass={n_pass} fail={n_fail}")
sys.exit(1 if n_fail else 0)