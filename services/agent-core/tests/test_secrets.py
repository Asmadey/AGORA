"""
Ключ провайдера шифруется вебом и расшифровывается воркером — байт в байт.

─── Что здесь стык ──────────────────────────────────────────────────────────
Шифрует Node (`apps/web/lib/server/secrets.ts`), расшифровывает Python. Формат
общий: `nonce(12) || tag(16) || ciphertext`, AES-256-GCM, ключ — SHA-256 от
`SETTINGS_SECRET`. Разойдясь хоть на порядок полей, стороны дадут ошибку
расшифровки посреди прогона — уже после оплаченных ffmpeg и транскрипции, и
выглядеть она будет как сбой провайдера, а не как несовпадение формата.

Проверка идёт настоящим шифротекстом от Node, а не «зашифровали и расшифровали
сами себя»: последнее прошло бы и при двух одинаково неверных реализациях.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_core.secrets import decrypt_secret, encrypt_secret

REPO = Path(__file__).resolve().parents[3]
SECRET = "парольная фраза для теста"
PLAIN = "sk-проверочный-ключ-провайдера-12345"


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SETTINGS_SECRET", SECRET)


def test_roundtrip_within_python():
    """Своё шифрование обратимо. Условие необходимое, но недостаточное."""
    assert decrypt_secret(encrypt_secret(PLAIN)) == PLAIN


def test_wrong_secret_does_not_decrypt(monkeypatch: pytest.MonkeyPatch):
    """
    Чужой ключ шифрования не расшифровывает.

    Иначе шифрование было бы декорацией: копия базы читалась бы любым, у кого
    есть код.
    """
    from cryptography.exceptions import InvalidTag

    blob = encrypt_secret(PLAIN)
    monkeypatch.setenv("SETTINGS_SECRET", "другая фраза")
    # InvalidTag, а не любое исключение: широкий except прошёл бы и на
    # опечатке в имени функции, ничего при этом не проверив.
    with pytest.raises(InvalidTag):
        decrypt_secret(blob)


def test_tampered_ciphertext_is_rejected():
    """
    Порченый байт отвергается, а не даёт мусор.

    GCM проверяет целостность: без этого подменённый в базе ключ уехал бы
    провайдеру как есть, и отказ выглядел бы проблемой провайдера.
    """
    from cryptography.exceptions import InvalidTag

    blob = bytearray(encrypt_secret(PLAIN))
    blob[-1] ^= 0x01
    with pytest.raises(InvalidTag):
        decrypt_secret(bytes(blob))


@pytest.mark.skipif(shutil.which("node") is None, reason="node не установлен")
def test_python_reads_what_node_wrote():
    """
    Настоящий стык: шифрует Node, расшифровывает Python.

    Это единственная проверка, которая ловит расхождение формата. Пара
    «зашифровали и расшифровали сами себя» прошла бы и при двух одинаково
    неверных реализациях по обе стороны.
    """
    script = f"""
      const {{ createCipheriv, createHash, randomBytes }} = require("node:crypto");
      const key = createHash("sha256").update({json.dumps(SECRET)}, "utf8").digest();
      const nonce = randomBytes(12);
      const cipher = createCipheriv("aes-256-gcm", key, nonce);
      const body = Buffer.concat([cipher.update({json.dumps(PLAIN)}, "utf8"), cipher.final()]);
      process.stdout.write(Buffer.concat([nonce, cipher.getAuthTag(), body]).toString("base64"));
    """
    out = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, check=True, timeout=60
    ).stdout.strip()

    import base64

    assert decrypt_secret(base64.b64decode(out)) == PLAIN


def test_web_and_worker_use_the_same_format():
    """
    Константы формата совпадают в обоих модулях.

    Дешёвая страховка на случай, когда node недоступен: длины полей заданы
    числами по обе стороны, и разъехаться они могут независимо.
    """
    ts = (REPO / "apps" / "web" / "lib" / "server" / "secrets.ts").read_text("utf-8")

    assert "const NONCE_BYTES = 12" in ts
    assert "const TAG_BYTES = 16" in ts
    assert "aes-256-gcm" in ts
    # Порядок полей: nonce, tag, тело. В Node он задан конкатенацией.
    assert "Buffer.concat([nonce, cipher.getAuthTag(), body])" in ts


def test_missing_secret_is_a_named_failure(monkeypatch: pytest.MonkeyPatch):
    """
    Без SETTINGS_SECRET — внятный отказ, а не тихий откат на ключ окружения.

    Молчаливый откат означал бы, что прогон пошёл под другим ключом, чем
    выбрала команда, и заметить это было бы нечем.
    """
    monkeypatch.delenv("SETTINGS_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="SETTINGS_SECRET"):
        decrypt_secret(os.urandom(64))
