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
        #: Замеры этапов. Подхватываются из снимка при первой записи, а не в
        #: конструкторе: воркер может перезапуститься посреди прогона (ради
        #: этого и заведён чекпоинтер), и новый писатель обязан продолжить счёт,
        #: а не начать с нуля — иначе «время обработки» покажет длительность
        #: последней попытки. Ленивость нужна затем, чтобы конструктор не ходил
        #: в сеть: его зовут и там, где писать ничего не собираются.
        self._timings: list[dict[str, Any]] | None = None

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
        payload["timings"] = self._track(node, status, payload["at"])
        return self._write(payload)

    def fail(self, node: str, error: str) -> dict[str, Any]:
        """
        Отказ с причиной.

        Причина — обязательный аргумент, а не необязательный: FAILED без текста
        отправляет пользователя читать логи воркера, к которым у него нет
        доступа.
        """
        at = time.time()
        return self._write({
            "task_id": self.task_id,
            "node": node,
            "status": "FAILED",
            "error": error,
            "at": at,
            # Упавший этап тоже имеет длительность. Иначе самый интересный для
            # разбора случай — «на чём встало и через сколько» — остаётся
            # единственным, о котором ничего не известно.
            "timings": self._track(node, "FAILED", at),
        })

    def _track(self, node: str, status: str, at: float) -> list[dict[str, Any]]:
        """
        Копит замеры этапов: RUNNING открывает запись, всё прочее закрывает.

        Длительность узла восстановить было нечем: снимок лежит в одном ключе и
        перезаписывается на каждое событие, а колонка `tasks.progress` заведена
        в схеме с первого дня и не пишется никем. Между тем «Время обработки» —
        показатель экрана, и на вопрос «почему прогон шёл сорок минут» без
        разбивки по этапам ответить нечем: транскрипция, разбор кадров и опрос
        персон отличаются по цене в разы.
        """
        if self._timings is None:
            raw = self.snapshot().get("timings")
            self._timings = list(raw) if isinstance(raw, list) else []

        if status == "RUNNING":
            self._timings.append({
                "node": node,
                "started_at": at,
                "finished_at": None,
                "duration_sec": None,
                "status": "RUNNING",
            })
            return self._timings

        for entry in reversed(self._timings):
            if entry.get("node") == node and entry.get("finished_at") is None:
                entry["finished_at"] = at
                entry["duration_sec"] = round(at - float(entry.get("started_at") or at), 3)
                entry["status"] = status
                return self._timings

        # Закрытие без открытия — узел, о начале которого никто не сообщил.
        # Запись всё равно заводится: «этап был» полезнее, чем его отсутствие.
        self._timings.append({
            "node": node, "started_at": None, "finished_at": at,
            "duration_sec": None, "status": status,
        })
        return self._timings

    def _write(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = json.dumps(payload, ensure_ascii=False)
        self.client.set(progress_key(self.task_id), message, ex=TTL_SECONDS)
        # Публикация после записи ключа, а не до: подписчик, разбуженный
        # сообщением, может тут же прочитать ключ, и порядок гарантирует, что он
        # прочитает новое значение, а не предыдущее.
        self.client.publish(progress_channel(self.task_id), message)
        return payload
