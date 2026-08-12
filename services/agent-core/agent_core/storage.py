"""
Забор исходного ролика: локальный путь или объект в S3.

Шов между #8 (загрузка) и #14 (препроцессинг). Веб кладёт видео прямо в S3 —
подписанной ссылкой, минуя себя, чтобы не проксировать гигабайты, — и передаёт в
задачу ключ объекта. Воркер до этой правки умел только локальные пути и
отказывался с `StageNotImplemented`.

Ни один CDD-тест этого не ловил: каждая стадия проверяла себя, а шов между
загрузкой и препроцессингом не проверял никто. Нашёл его первый сквозной прогон
(#22), и это ровно то, ради чего сквозной гейт существует.

─── Три свойства, вокруг которых написан модуль ─────────────────────────────
**Скачивание атомарно.** Файл появляется на своём месте целиком или не
появляется вовсе. Обрезанный mp4 — худший исход: он существует, кэш считает его
готовым, ffprobe разбирает начало, и прогон идёт по неполному ролику. Отличить
такой отчёт от честного нельзя ничем.

**Скачивание кэшируется.** Граф возобновляется с чекпоинта, и после отказа на
любом узле ниже препроцессинга прогон начнётся заново отсюда. Повторное
скачивание двенадцатиминутного ролика — минуты и трафик на каждом перезапуске.

**Отказы называют причину.** `NoCredentialsError` в логе воркера читается как
дефект кода, а не как незаполненный `.env.local`, и уводит на час.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Protocol


class S3ConfigError(RuntimeError):
    """Настройки S3 неполны. Текст обязан называть переменные."""


class S3ObjectMissing(RuntimeError):
    """Объекта с таким ключом в бакете нет. Текст обязан называть ключ."""


#: Ключ объекта в бакете: `tenants/<uuid>/uploads/<uuid>.<ext>`. Формат задан
#: вебом (`apps/web/lib/server/s3.ts`) и продублирован здесь намеренно: воркер
#: обязан отличать ключ от локального пути ДО обращения к сети, иначе опечатка в
#: пути превратится в поход в S3 и отказ «объект не найден» вместо «файла нет».
_S3_KEY = re.compile(r"^tenants/[0-9a-f-]{36}/uploads/[^/]+$")


class S3Client(Protocol):
    """Минимум, который нужен модулю. Подделывается в тестах одним методом."""

    def download(self, key: str, dest: Path) -> None: ...


def looks_like_s3_key(ref: str) -> bool:
    """
    Ключ объекта, а не путь в файловой системе.

    Проверка по форме, а не «нет такого файла — значит S3». Отрицательная
    проверка ошибается там, где ошибиться нельзя: опечатка в локальном пути дала
    бы поход в бакет и сообщение «объект не найден», по которому искали бы
    пропавшую загрузку вместо опечатки.
    """
    return bool(_S3_KEY.match(ref.strip()))


class Boto3S3(S3Client):
    """
    Клиент поверх boto3. Создаётся лениво — импорт стоит заметного времени.

    `path`-стиль адресации задан явно: у TimeWeb S3 работает он, а boto3 по
    умолчанию пробует virtual-hosted, и отказ выглядит как DNS-ошибка на
    несуществующем поддомене — то есть как проблема сети, а не настройки.
    """

    def __init__(self) -> None:
        missing = [
            name for name in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY")
            if not os.environ.get(name)
        ]
        if missing:
            raise S3ConfigError(
                f"не заданы {', '.join(missing)} — воркеру нечем забрать ролик из "
                f"хранилища. Переменные те же, что у веба, см. .env.local"
            )

        import boto3
        from botocore.config import Config

        self.bucket = os.environ["S3_BUCKET"]
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=os.environ["S3_ENDPOINT"],
            aws_access_key_id=os.environ["S3_ACCESS_KEY"],
            aws_secret_access_key=os.environ["S3_SECRET_KEY"],
            region_name=os.environ.get("S3_REGION", "ru-1"),
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )

    def download(self, key: str, dest: Path) -> None:
        from botocore.exceptions import ClientError

        try:
            self._client.download_file(self.bucket, key, str(dest))
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            # 404 и 403 различаются намеренно: «объекта нет» отправляет смотреть
            # загрузку, «доступ запрещён» — ключи и политику бакета. Общее
            # сообщение отправило бы искать не там.
            if code in ("404", "NoSuchKey", "NotFound"):
                raise S3ObjectMissing(
                    f"в бакете {self.bucket} нет объекта {key}. Загрузка не "
                    f"завершилась либо ключ записан в задачу неверно"
                ) from None
            if code in ("403", "AccessDenied"):
                raise S3ConfigError(
                    f"доступ к {self.bucket}/{key} запрещён (403). Проверьте "
                    f"S3_ACCESS_KEY, S3_SECRET_KEY и политику бакета"
                ) from None
            raise


def fetch_source(
    ref: str,
    *,
    workdir: Path,
    client: S3Client | None = None,
) -> Path:
    """
    Локальный путь к ролику. Скачивает из S3, если `ref` — ключ объекта.

    `client` подставляется в тестах; в работе создаётся сам и только тогда,
    когда действительно нужен, — локальному пути S3 не требуется вовсе.
    """
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("video_ref пуст: забирать нечего")

    if not looks_like_s3_key(ref):
        path = Path(ref)
        if path.exists():
            return path
        raise FileNotFoundError(
            f"{ref} — не ключ объекта в S3 и не существующий файл. Ключ имеет вид "
            f"tenants/<uuid>/uploads/<имя>"
        )

    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / Path(ref).name
    if target.exists() and target.stat().st_size > 0:
        return target

    if client is None:
        client = Boto3S3()

    # Скачиваем во временное имя рядом и переименовываем: rename в пределах
    # одной файловой системы атомарен, поэтому файл под итоговым именем либо
    # целый, либо его нет. Отказ по пути не оставляет обрезанного mp4.
    staging = target.with_suffix(target.suffix + ".part")
    try:
        client.download(ref, staging)
        staging.replace(target)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise

    return target
