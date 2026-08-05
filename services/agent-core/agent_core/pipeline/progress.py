"""
Прогресс прогона в Valkey (Decision Log #3), источник для SSE-экрана (#12).

─── Ключ и канал, а не только канал ─────────────────────────────────────────
Pub/Sub ничего не помнит. Подписчик, подключившийся к середине прогона, не
получит ни одного из уже отправленных сообщений — а экран прогресса открывают
именно так: пользователь запустил исследование, закрыл вкладку и вернулся через
десять минут.

Поэтому текущее состояние всегда лежит в ключе `agora:progress:<task_id>`, а
канал `agora:progress:<task_id>` только уведомляет о его изменении. При
переподключении SSE-обработчик сперва отдаёт снимок из ключа, потом
подписывается на канал. Обратный порядок теряет события, случившиеся между
чтением и подпиской.

─── Почему TTL, а не удаление по завершении ─────────────────────────────────
Прогон, упавший вместе с воркером, не удалит за собой ничего. Без TTL ключи
копились бы до заполнения памяти Valkey — то есть отказ выглядел бы как отказ
брокера очередей, а не как утечка снимков прогресса. TTL продлевается на каждой
записи, поэтому долгий прогон не теряет свой ключ на середине.
"""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

#: Сутки после последней записи. Достаточно, чтобы разобраться в упавшем ночью
#: прогоне, и мало, чтобы копить их месяцами.
TTL_SECONDS = 24 * 60 * 60

_PREFIX = "agora:progress:"


def progress_key(task_id: str) -> str:
    return f"{_PREFIX}{task_id}"


def progress_channel(task_id: str) -> str:
    return f"{_PREFIX}{task_id}"


class ValkeyLike(Protocol):
    """Часть API redis-py, которой достаточно. Ничего из Redis Stack."""

    def set(self, key: str, value: Any, **kwargs: Any) -> Any: ...
    def get(self, key: str) -> Any: ...
    def publish(self, channel: str, message: Any) -> Any: ...


class ProgressWriter:
    """
    Пишет снимок прогресса и уведомляет подписчиков.

    Объект намеренно не хранит состояние между вызовами: снимок читается из
    Valkey. Иначе два воркера, подхвативших один прогон после перезапуска,
    затирали бы прогресс друг друга своими локальными представлениями — а такой
    дефект виден только как «прогресс скачет назад», то есть как дефект
    интерфейса.
    """

    def __init__(self, client: ValkeyLike, task_id: str) -> None:
        self.client = client
        self.task_id = task_id

    # ── чтение ──────────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Текущее состояние. Пустой словарь — прогон ещё ничего не написал."""
        raw = self.client.get(progress_key(self.task_id))
        if not raw:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Битый снимок не должен ронять экран прогресса: показать «нет
            # данных» честнее, чем 500 на странице запущенного исследования.
            return {}

    # ── запись ──────────────────────────────────────────────────────────────

    def emit(
        self,
        node: str,
        status: str,
        detail: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Смена узла или его состояния. Возвращает записанный снимок."""
        payload: dict[str, Any] = {
            "task_id": self.task_id,
            "node": node,
            "status": status,
            "at": time.time(),
        }
        if detail:
            payload["detail"] = detail
        payload.update(extra)
        return self._write(payload)

    def fail(self, node: str, error: str) -> dict[str, Any]:
        """
        Отказ с причиной.

        Причина — обязательный аргумент, а не необязательный: FAILED без текста
        отправляет пользователя читать логи воркера, к которым у него нет
        доступа.
        """
        return self._write({
            "task_id": self.task_id,
            "node": node,
            "status": "FAILED",
            "error": error,
            "at": time.time(),
        })

    def _write(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = json.dumps(payload, ensure_ascii=False)
        self.client.set(progress_key(self.task_id), message, ex=TTL_SECONDS)
        # Публикация после записи ключа, а не до: подписчик, разбуженный
        # сообщением, может тут же прочитать ключ, и порядок гарантирует, что он
        # прочитает новое значение, а не предыдущее.
        self.client.publish(progress_channel(self.task_id), message)
        return payload
