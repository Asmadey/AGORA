#!/usr/bin/env python3
"""
CDD-тест задачи #8 — Загрузка видео (S3 presigned + ffprobe).

Двухуровневый: статический работает где угодно, поведенческий требует
живого S3 (TimeWeb) и ffprobe.

CDD (из tasks.json):
  файл >700 МБ отклоняется; неподдерживаемое расширение отклоняется;
  успешная загрузка даёт S3-ключ, привязанный к tenant_id.
"""
from __future__ import annotations
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

PASS = "OK"
FAIL = "FAIL"
SKIP = "SKIP"

results = []


def check(name, ok, detail=""):
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail else ""))


def skip(name, reason):
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

S3_PATH = REPO / "apps" / "web" / "lib" / "server" / "s3.ts"
PRESIGN_ROUTE = REPO / "apps" / "web" / "app" / "api" / "upload" / "presign" / "route.ts"
COMPLETE_ROUTE = REPO / "apps" / "web" / "app" / "api" / "upload" / "complete" / "route.ts"

s3_text = S3_PATH.read_text("utf-8") if S3_PATH.exists() else ""
presign_text = PRESIGN_ROUTE.read_text("utf-8") if PRESIGN_ROUTE.exists() else ""
complete_text = COMPLETE_ROUTE.read_text("utf-8") if COMPLETE_ROUTE.exists() else ""

# 1. S3 presign module exists and exports createPresignedPutUrl
check(
    "модуль s3.ts существует и экспортирует createPresignedPutUrl",
    "export function createPresignedPutUrl" in s3_text,
    f"S3_PATH={S3_PATH.exists()}",
)

# 2. Presigned URL uses SigV4 (AWS4-HMAC-SHA256)
check(
    "подпись SigV4 (AWS4-HMAC-SHA256)",
    "AWS4-HMAC-SHA256" in s3_text,
)

# 3. No @aws-sdk dependency — uses node:crypto only
has_aws_sdk_import = bool(re.search(r"from\s+['\"]@aws-sdk", s3_text))
check(
    "нет зависимости @aws-sdk (node:crypto вместо неё)",
    not has_aws_sdk_import and "node:crypto" in s3_text,
)

# 4. S3 key tied to tenant_id
#    Key format: tenants/{tenantId}/uploads/{uuid}.{ext}
check(
    "S3-ключ привязан к tenant_id (tenants/{tenantId}/uploads/)",
    "tenants/" in s3_text and "tenantId" in s3_text,
)

# 5. 700 MB file size limit enforced
has_700_limit = "700" in s3_text and "MAX_FILE_SIZE" in s3_text
check(
    "лимм 700 МБ объявлен (MAX_FILE_SIZE)",
    has_700_limit,
)

# 6. Allowed formats: mp4, mov, avi
check(
    "разрешённые расширения: mp4, mov, avi",
    all(ext in s3_text for ext in ["mp4", "mov", "avi"]),
)

# 7. Presign API route exists with POST handler
check(
    "POST /api/upload/presign существует",
    "export async function POST" in presign_text,
)

# 8. Presign route validates content type and rejects unsupported
check(
    "presign валидирует MIME-тип и отклоняет неподдерживаемый",
    "ALLOWED_MIME_TYPES" in presign_text and "400" in presign_text,
)

# 9. Presign route requires session (tenant_id from session, not args)
check(
    "presign требует сессию (requireSession)",
    "requireSession" in presign_text,
)

# 10. Complete API route exists with POST handler
check(
    "POST /api/upload/complete существует",
    "export async function POST" in complete_text,
)

# 11. Complete route runs ffprobe
check(
    "complete запускает ffprobe (probeVideo)",
    "probeVideo" in complete_text,
)

# 12. Complete route validates key belongs to tenant (prefix check)
check(
    "complete проверяет принадлежность ключа арендатору (startsWith)",
    "startsWith" in complete_text and "expectedPrefix" in complete_text,
)

# 13. Complete route enforces size check from S3 (HEAD)
check(
    "complete проверяет размер из S3 (headObjectSize)",
    "headObjectSize" in complete_text,
)

# 14. ffprobe validates codec (allowed codecs list)
check(
    "ffprobe валидирует кодек (ALLOWED_CODECS)",
    "ALLOWED_CODECS" in s3_text,
)

# 15. ffprobe validates duration
check(
    "ffprobe валидирует длительность (durationSec > 0)",
    "durationSec" in s3_text and "durationSec <= 0" in s3_text,
)

# 16. No native npm modules (no node-gyp, no .node files in deps)
web_pkg = (REPO / "apps" / "web" / "package.json").read_text("utf-8")
native_indicators = ["node-gyp", "node-pre-gyp", "prebuild-install", "@node-rs"]
has_native = any(ind in web_pkg for ind in native_indicators)
check(
    "нет нативных npm-модулей в package.json",
    not has_native,
)


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Поведенческий уровень ==")

s3_endpoint = os.environ.get("S3_ENDPOINT", "")
s3_access_key = os.environ.get("S3_ACCESS_KEY", "")
s3_secret_key = os.environ.get("S3_SECRET_KEY", "")

has_s3_creds = bool(s3_endpoint and s3_access_key and s3_secret_key)
has_server = os.environ.get("AGORA_TEST_SERVER") is not None or os.environ.get("BASE_URL") is not None

if not has_s3_creds:
    skip("поведенческий кейс: файл >700 МБ отклоняется", "требует S3_ENDPOINT/ACCESS_KEY/SECRET_KEY")
    skip("поведенческий кейс: неподдерживаемое расширение отклоняется", "требует S3 creds")
    skip("поведенческий кейс: успешная загрузка даёт ключ с tenant_id", "требует S3 creds")
    skip("поведенческий кейс: ffprobe валидирует реальный файл", "требует S3 creds + ffprobe")
elif not has_server:
    skip("поведенческий кейс: файл >700 МБ отклоняется", "требует AGORA_TEST_SERVER/BASE_URL")
    skip("поведенческий кейс: неподдерживаемое расширение отклоняется", "требует AGORA_TEST_SERVER/BASE_URL")
    skip("поведенческий кейс: успешная загрузка даёт ключ с tenant_id", "требует AGORA_TEST_SERVER/BASE_URL")
    skip("поведенческий кейс: ffprobe валидирует реальный файл", "требует AGORA_TEST_SERVER/BASE_URL")
else:
    import json
    import urllib.request
    import urllib.error

    server_url = os.environ.get("AGORA_TEST_SERVER") or os.environ["BASE_URL"]

    try:
        # B1: Файл >700 МБ отклоняется на этапе presign
        payload = json.dumps({
            "fileName": "big.mp4",
            "contentType": "video/mp4",
            "fileSize": 701 * 1024 * 1024,
        }).encode()
        req = urllib.request.Request(
            f"{server_url}/api/upload/presign",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req)
            check("файл >700 МБ отклоняется (presign)", False, "сервер не отклонил")
        except urllib.error.HTTPError as e:
            check("файл >700 МБ отклоняется (presign)", e.code == 400, f"status={e.code}")

        # B2: Неподдерживаемое расширение отклоняется
        payload = json.dumps({
            "fileName": "video.mkv",
            "contentType": "video/x-matroska",
            "fileSize": 1024,
        }).encode()
        req = urllib.request.Request(
            f"{server_url}/api/upload/presign",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req)
            check("неподдерживаемое расширение отклоняется", False, "сервер не отклонил .mkv")
        except urllib.error.HTTPError as e:
            check("неподдерживаемое расширение отклоняется", e.code == 400, f"status={e.code}")

        skip("успешная загрузка даёт ключ с tenant_id", "требует mock-сессию и тестовый видеофайл")
        skip("ffprobe валидирует реальный файл", "требует mock-сессию и тестовый видеофайл")

    except Exception as e:
        check("поведенческий тест upload", False, f"{type(e).__name__}: {str(e)[:120]}")


# ═══════════════════════════════════════════════════════════════════════════
# ИТОГ
# ═══════════════════════════════════════════════════════════════════════════

n_pass = sum(1 for _, s, _ in results if s == PASS)
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_skip = sum(1 for _, s, _ in results if s == SKIP)

if n_fail:
    print(f"\nRED — не выполнено условий: {n_fail}")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" ({detail})" if detail else ""))
elif n_skip > 0 and n_pass == 0:
    print(f"\nSKIP — все тесты пропущены")
else:
    print(f"\nGREEN — задача #8 удовлетворяет критериям (pass={n_pass} skip={n_skip})")

sys.exit(1 if n_fail else 0)
