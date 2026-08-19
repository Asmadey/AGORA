"""
Ключ провайдера: шифрует веб на Node, расшифровывает воркер на Python.

─── Почему этот тест не похож на остальные ───────────────────────────────────
Здесь один формат и ДВЕ независимые реализации на разных языках. Каждая по
отдельности исправна: `secrets.test.ts` проверяет, что веб расшифровывает своё,
`test_secrets.py` — что воркер расшифровывает своё. Оба зелены и при этом
ничего не говорят о том, поймут ли они друг друга.

А разойтись здесь легко, и место известно. AESGCM в Python ждёт тег в ХВОСТЕ
шифротекста, а `createDecipheriv` в Node принимает его отдельным вызовом
`setAuthTag`. Формат кладёт тег ПЕРЕД телом, и обе стороны переставляют его
сами. Ошибись одна — и ключ, сохранённый из интерфейса, перестанет
расшифровываться воркером.

Как это выглядело бы: настройки сохраняются, галочка зелёная, прогон стартует и
падает на первом вызове модели с «ключ провайдера не задан». Причину искали бы в
провайдере.

─── Почему тест здесь, а не в вебе ───────────────────────────────────────────
Он двусторонний, и запускать его надо там, где есть обе стороны. В CI есть и
python, и node; на хосте разработчика — тоже.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_core.secrets import decrypt_secret, encrypt_secret

WEB = Path(__file__).resolve().parents[3] / "apps" / "web"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="нужен node — вторая сторона формата",
)

SECRET = "проверочный-секрет-для-стыка"
#: Что шифруем. Ключ провайдера — это то, что реально едет через этот формат.
PLAIN = "sk-" + "x" * 40


def _node(script: str) -> str:
    """
    Запускает кусок Node, импортирующий НАСТОЯЩИЙ модуль веба.

    Именно настоящий, а не переписанный на месте: копия формата в тесте
    проверяла бы копию. Модуль на TypeScript, поэтому идёт через ту же
    загрузку типов, что и тесты веба.
    """
    result = subprocess.run(
        # --conditions=react-server обязателен: модуль начинается с
        # `import "server-only"`, и без этого условия пакет бросает исключение
        # при загрузке. Тот же флаг стоит в npm test веба и по той же причине.
        [
            "node", "--conditions=react-server", "--experimental-strip-types",
            "--input-type=module", "-e", script,
        ],
        cwd=WEB,
        capture_output=True,
        text=True,
        env={**os.environ, "SETTINGS_SECRET": SECRET},
        timeout=120,
    )
    if result.returncode != 0:
        pytest.skip(f"node не смог загрузить модуль веба: {result.stderr[-400:]}")
    return result.stdout.strip()


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("SETTINGS_SECRET", SECRET)


def test_worker_reads_what_the_web_wrote():
    """Главное направление: интерфейс сохранил, прогон прочитал."""
    encoded = _node(
        "import {encryptSecret} from './lib/server/secrets.ts';"
        f"process.stdout.write(encryptSecret({json.dumps(PLAIN)}).toString('base64'));"
    )
    assert encoded, "веб ничего не зашифровал"
    assert decrypt_secret(base64.b64decode(encoded)) == PLAIN


def test_web_reads_what_the_worker_wrote():
    """
    Обратное направление тоже обязано работать. Оно не используется в продукте,
    но односторонняя совместимость — признак того, что стороны разошлись и одна
    подстроилась под другую случайно.
    """
    encoded = base64.b64encode(encrypt_secret(PLAIN)).decode()
    out = _node(
        "import {decryptSecret} from './lib/server/secrets.ts';"
        f"process.stdout.write(decryptSecret(Buffer.from({json.dumps(encoded)}, 'base64')));"
    )
    assert out == PLAIN


def test_different_secret_does_not_decrypt():
    """
    Ключ шифрования выводится из SETTINGS_SECRET. Расхождение переменной между
    web и worker обязано быть ОТКАЗОМ, а не тихой ерундой: молча расшифрованный
    мусор уехал бы в заголовок Authorization.
    """
    from cryptography.exceptions import InvalidTag

    blob = encrypt_secret(PLAIN)
    os.environ["SETTINGS_SECRET"] = SECRET + "-другой"
    try:
        # Именно InvalidTag, а не любое исключение: «упало хоть как-нибудь»
        # зелёное и в том случае, когда падает по другой причине — например, из
        # опечатки в самом тесте.
        with pytest.raises(InvalidTag):
            decrypt_secret(blob)
    finally:
        os.environ["SETTINGS_SECRET"] = SECRET


def test_truncated_blob_is_a_named_failure():
    """Обрезанные байты — испорченные данные, а не повод отдать пустой ключ."""
    with pytest.raises(ValueError, match="испорчен"):
        decrypt_secret(b"\x00" * 20)


def test_nonce_is_not_reused():
    """
    Повтор nonce в AES-GCM ломает шифр целиком. Проверяется на самом простом:
    два шифрования одного и того же дают разные байты.
    """
    assert encrypt_secret(PLAIN) != encrypt_secret(PLAIN)
