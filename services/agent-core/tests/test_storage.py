"""
Тесты забора исходного ролика (шов между #8 и #14).

Веб кладёт видео в S3 и передаёт в задачу ключ объекта; воркер до этой правки
умел только локальные пути и отказывался с `StageNotImplemented`. Ни один
CDD-тест этого не ловил: каждая стадия проверяла себя, а шов между загрузкой и
препроцессингом не проверял никто. Нашёл его первый сквозной прогон (#22) —
ровно для этого сквозной гейт и существует.

Тесты работают без сети: клиент S3 подставляется поддельный. Проверяется не то,
что boto3 умеет качать, а то, как узел ведёт себя на отказах — потому что
ломается именно это.
"""

from __future__ import annotations

import pytest

from agent_core.storage import (
    S3ConfigError,
    S3ObjectMissing,
    fetch_source,
    looks_like_s3_key,
)


class FakeS3:
    """Достаточно узкая подделка: отдаёт байты по ключу либо сообщает, что его нет."""

    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.calls: list[str] = []

    def download(self, key: str, dest) -> None:
        self.calls.append(key)
        if key not in self.objects:
            raise S3ObjectMissing(f"нет объекта {key}")
        dest.write_bytes(self.objects[key])


KEY = "tenants/de15d1e3-e2f6-41c7-966d-91c186046066/uploads/abc.mp4"


# ─── Что считается ключом S3 ─────────────────────────────────────────────────


def test_local_path_is_not_a_key():
    assert not looks_like_s3_key("/tmp/agora/video.mp4")
    assert not looks_like_s3_key("./fixtures/short_60s.mp4")


def test_tenant_upload_path_is_a_key():
    assert looks_like_s3_key(KEY)


# ─── Локальный путь продолжает работать ──────────────────────────────────────


def test_existing_local_file_is_returned_as_is(tmp_path):
    """
    Прежнее поведение не сломано.

    На локальные пути опираются и фикстуры прогонщика, и ручной запуск на
    машине разработчика. Замена одного способа другим сделала бы правку
    несовместимой там, где она не обязана быть несовместимой.
    """
    local = tmp_path / "video.mp4"
    local.write_bytes(b"\x00\x01")
    client = FakeS3({})

    got = fetch_source(str(local), workdir=tmp_path, client=client)

    assert got == local
    assert client.calls == [], "локальный файл не должен ходить в S3"


# ─── Скачивание ──────────────────────────────────────────────────────────────


def test_key_is_downloaded_into_workdir(tmp_path):
    client = FakeS3({KEY: b"video-bytes"})

    got = fetch_source(KEY, workdir=tmp_path, client=client)

    assert got.parent == tmp_path
    assert got.read_bytes() == b"video-bytes"
    assert client.calls == [KEY]


def test_second_call_does_not_download_again(tmp_path):
    """
    Кэш обязателен, а не приятен.

    Граф возобновляется с чекпоинта: после отказа на любом узле ниже
    препроцессинга прогон начнётся заново с этого места. Повторное скачивание
    двенадцатиминутного ролика — это минуты и трафик на каждом перезапуске, и
    заметно это станет на длинном режиме, где перезапусков больше всего.
    """
    client = FakeS3({KEY: b"video-bytes"})

    first = fetch_source(KEY, workdir=tmp_path, client=client)
    second = fetch_source(KEY, workdir=tmp_path, client=client)

    assert first == second
    assert client.calls == [KEY], f"скачано повторно: {client.calls}"


def test_partial_download_leaves_no_file(tmp_path):
    """
    Оборванное скачивание не оставляет обрезанный файл.

    Обрезанный mp4 — худший исход из возможных: он существует, кэш считает его
    готовым, ffprobe разбирает начало, и прогон идёт по неполному ролику. Отказ
    в середине обязан не оставить ничего, чтобы следующая попытка скачала заново.
    """

    class Broken:
        def download(self, key: str, dest) -> None:
            dest.write_bytes(b"half-written")
            raise OSError("соединение оборвано")

    with pytest.raises(OSError):
        fetch_source(KEY, workdir=tmp_path, client=Broken())

    assert list(tmp_path.iterdir()) == [], f"остались файлы: {list(tmp_path.iterdir())}"


# ─── Отказы называют причину ─────────────────────────────────────────────────


def test_missing_object_names_the_key(tmp_path):
    client = FakeS3({})
    with pytest.raises(S3ObjectMissing) as exc:
        fetch_source(KEY, workdir=tmp_path, client=client)
    assert KEY in str(exc.value)


def test_missing_config_names_the_variable(tmp_path, monkeypatch):
    """
    Без настроек S3 отказ называет переменную, а не падает внутри boto3.

    `botocore.exceptions.NoCredentialsError` в логе воркера читается как дефект
    кода, а не как незаполненный `.env.local`, и уводит на час.
    """
    for var in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(S3ConfigError) as exc:
        fetch_source(KEY, workdir=tmp_path)
    assert "S3_" in str(exc.value)


def test_empty_ref_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        fetch_source("", workdir=tmp_path)
