"""
Расшифровка секретов арендатора: ключ провайдера, заданный из интерфейса.

─── Формат ──────────────────────────────────────────────────────────────────
AES-256-GCM, один буфер: ``nonce(12) || tag(16) || ciphertext``. Формат обязан
совпадать с `apps/web/lib/server/secrets.ts` — шифрует веб, расшифровывает
воркер. Разойдясь, стороны дадут ошибку посреди прогона, уже после оплаченных
ffmpeg и транскрипции; совпадение держит test_secrets.py.

─── Ключ шифрования ─────────────────────────────────────────────────────────
``SETTINGS_SECRET`` из окружения обоих сервисов, свёрнутый SHA-256 до 32 байт.
Свёртка, а не требование ровно 32 байт: оператор на практике вписывает
парольную фразу, и отказ на длине означал бы неработающий продукт там, где
нужен работающий.

В базу ключ шифрования не попадает никогда: замок и ключ в одном ящике — это не
шифрование, а его имитация.

─── Почему не в снимок задачи ───────────────────────────────────────────────
Ключ читается из `settings` в момент прогона, а не кладётся в
`tasks.settings_snapshot`. Снимок живёт столько же, сколько отчёт, и копия
секрета в каждой строке `tasks` — это тот же секрет, размноженный по резервным
копиям без единого способа его отозвать.
"""

from __future__ import annotations

import hashlib
import os

NONCE_BYTES = 12
TAG_BYTES = 16


class SecretsUnavailable(RuntimeError):
    """SETTINGS_SECRET не задан — расшифровать нечем."""


def secrets_available() -> bool:
    return bool(os.environ.get("SETTINGS_SECRET"))


def _key() -> bytes:
    secret = os.environ.get("SETTINGS_SECRET")
    if not secret:
        raise SecretsUnavailable(
            "SETTINGS_SECRET не задан: ключ провайдера, сохранённый из интерфейса, "
            "расшифровать нечем. Переменная обязана совпадать у web и worker"
        )
    return hashlib.sha256(secret.encode("utf-8")).digest()


def decrypt_secret(blob: bytes) -> str:
    """Расшифровывает то, что зашифровал веб. Порченые байты — исключение."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if len(blob) <= NONCE_BYTES + TAG_BYTES:
        raise ValueError("зашифрованный ключ короче служебных полей — данные испорчены")
    nonce = blob[:NONCE_BYTES]
    tag = blob[NONCE_BYTES : NONCE_BYTES + TAG_BYTES]
    body = blob[NONCE_BYTES + TAG_BYTES :]
    # AESGCM ждёт tag в хвосте шифротекста, а формат кладёт его перед — как в
    # Node, где getAuthTag() отдаёт его отдельно. Переставляем здесь, а не
    # меняем формат: формат общий, и подгонять его под удобство одной стороны
    # значит ломать другую.
    return AESGCM(_key()).decrypt(nonce, body + tag, None).decode("utf-8")


def encrypt_secret(plain: str) -> bytes:
    """Обратная операция. Нужна тестам совместимости, в конвейере не вызывается."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(_key()).encrypt(nonce, plain.encode("utf-8"), None)
    body, tag = sealed[:-TAG_BYTES], sealed[-TAG_BYTES:]
    return nonce + tag + body


def tenant_api_key(tenant_id: str) -> str | None:
    """
    Ключ провайдера арендатора либо None, если задан только в окружении.

    None — законный и самый частый случай: так работают все прогоны до того, как
    ключ впервые задали в интерфейсе. Отличать его от ошибки расшифровки
    обязательно, поэтому ошибка поднимается, а не превращается в None: молчаливый
    откат на ключ окружения означал бы, что прогон пошёл под чужим ключом, и
    заметить это было бы нечем.
    """
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return None

    import psycopg

    from .db import tenant_scope

    with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
        cur.execute(
            "SELECT provider_api_key FROM settings WHERE tenant_id = app.current_tenant()"
        )
        row = cur.fetchone()

    if not row or row[0] is None:
        return None
    return decrypt_secret(bytes(row[0]))
