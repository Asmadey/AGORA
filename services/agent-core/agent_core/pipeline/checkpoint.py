"""
Чекпоинтер LangGraph на голом Valkey.

─── Почему свой, а не langgraph-checkpoint-redis ────────────────────────────
Готовый пакет тянет redisvl и требует модулей RediSearch и RedisJSON, то есть
Redis Stack. В развёртывании стоит Valkey 9.1 (Decision Log #3), и этих модулей
в нём нет — их вообще нельзя доставить в Valkey, это отдельные проприетарные
модули Redis Ltd.

Опасность здесь не в том, что пакет не работает, а в том, КОГДА это выясняется.
Устанавливается он без единого предупреждения; на машине разработчика с Redis
Stack тесты проходят; отказ наступает при первой записи чекпоинта — то есть
после того, как отработали ffprobe, транскрипция 15-минутного ролика и первые
вызовы VLM. Оплаченная работа теряется, а в логе стоит `unknown command 'JSON.SET'`.

Поэтому здесь только те команды, которые есть в любом Valkey: SET, GET, DELETE,
SCAN. Ни одного вызова из пространств JSON.* и FT.*.

─── Что именно требуется от чекпоинтера ─────────────────────────────────────
LangGraph вызывает четыре метода: put (сохранить снимок после шага), put_writes
(частичные записи узла до завершения шага), get_tuple (последний или конкретный
снимок), list (история). Остальное в BaseCheckpointSaver имеет разумные
умолчания.

put_writes хранится наравне со снимком, а не в памяти процесса. В памяти он
переживёт исключение внутри одного процесса — но не перезапуск воркера, ради
которого чекпоинтер и заведён. Дефект был бы избирательным: падение узла
резюмируется правильно, падение процесса теряет последний шаг.

─── Сериализация ────────────────────────────────────────────────────────────
Берётся JsonPlusSerializer самого LangGraph, а не json.dumps: в состоянии живут
объекты, которые json не умеет (datetime, UUID, pydantic-модели узлов). Он
отдаёт пару (тип, байты); байты кладутся в JSON через base64, чтобы значение
ключа оставалось текстом и его можно было прочитать глазами при разборе
упавшего прогона.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator, Sequence
from typing import Any, Protocol

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

#: Сутки после последней записи — как у снимков прогресса. Прогон, упавший
#: вместе с воркером, за собой не приберёт, а без срока жизни чекпоинты копятся
#: до заполнения памяти Valkey.
TTL_SECONDS = 24 * 60 * 60

_CP = "agora:cp:"
_WRITES = "agora:cpw:"
_LATEST = "agora:cplatest:"


class ValkeyLike(Protocol):
    """Часть API redis-py, которой достаточно. Ничего из Redis Stack."""

    def set(self, key: str, value: Any, **kwargs: Any) -> Any: ...
    def get(self, key: str) -> Any: ...
    def delete(self, *keys: str) -> Any: ...
    def scan_iter(self, match: str | None = None, **kwargs: Any) -> Iterator[Any]: ...


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


class ValkeyCheckpointSaver(BaseCheckpointSaver):
    """Синхронный чекпоинтер. Асинхронные методы не нужны: граф крутится в Celery."""

    def __init__(self, client: ValkeyLike, ttl_seconds: int = TTL_SECONDS) -> None:
        super().__init__(serde=JsonPlusSerializer())
        self.client = client
        self.ttl = ttl_seconds

    # ── ключи ───────────────────────────────────────────────────────────────

    @staticmethod
    def _ids(config: dict[str, Any]) -> tuple[str, str, str | None]:
        cfg = config.get("configurable") or {}
        return (
            str(cfg["thread_id"]),
            str(cfg.get("checkpoint_ns") or ""),
            cfg.get("checkpoint_id"),
        )

    def _cp_key(self, thread: str, ns: str, checkpoint_id: str) -> str:
        return f"{_CP}{thread}:{ns}:{checkpoint_id}"

    def _writes_key(self, thread: str, ns: str, checkpoint_id: str) -> str:
        return f"{_WRITES}{thread}:{ns}:{checkpoint_id}"

    def _latest_key(self, thread: str, ns: str) -> str:
        return f"{_LATEST}{thread}:{ns}"

    # ── сериализация ────────────────────────────────────────────────────────

    def _pack(self, value: Any) -> str:
        type_, blob = self.serde.dumps_typed(value)
        return json.dumps({"t": type_, "b": base64.b64encode(blob).decode("ascii")})

    def _unpack(self, raw: Any) -> Any:
        payload = json.loads(_text(raw) or "{}")
        return self.serde.loads_typed((payload["t"], base64.b64decode(payload["b"])))

    def _put(self, key: str, value: str) -> None:
        self.client.set(key, value, ex=self.ttl)

    # ── контракт BaseCheckpointSaver ────────────────────────────────────────

    def put(
        self,
        config: dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Any,
    ) -> dict[str, Any]:
        thread, ns, parent_id = self._ids(config)
        checkpoint_id = checkpoint["id"]

        self._put(
            self._cp_key(thread, ns, checkpoint_id),
            self._pack({"checkpoint": checkpoint, "metadata": metadata, "parent": parent_id}),
        )
        # Указатель на последний снимок ветки: без него resume не знает, откуда
        # продолжать, а перебирать SCAN'ом и сортировать пришлось бы на каждом шаге.
        self._put(self._latest_key(thread, ns), checkpoint_id)

        return {
            "configurable": {
                "thread_id": thread,
                "checkpoint_ns": ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: dict[str, Any],
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread, ns, checkpoint_id = self._ids(config)
        if checkpoint_id is None:
            return

        key = self._writes_key(thread, ns, checkpoint_id)
        stored: list[dict[str, Any]] = []
        existing = self.client.get(key)
        if existing:
            stored = json.loads(_text(existing) or "[]")

        for channel, value in writes:
            stored.append({
                "task_id": task_id,
                "task_path": task_path,
                "channel": channel,
                "value": self._pack(value),
            })

        self._put(key, json.dumps(stored, ensure_ascii=False))

    def get_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        thread, ns, checkpoint_id = self._ids(config)
        if checkpoint_id is None:
            checkpoint_id = _text(self.client.get(self._latest_key(thread, ns)))
        if not checkpoint_id:
            return None

        raw = self.client.get(self._cp_key(thread, ns, checkpoint_id))
        if raw is None:
            return None
        stored = self._unpack(raw)

        parent_id = stored.get("parent")
        parent_config = (
            {"configurable": {"thread_id": thread, "checkpoint_ns": ns,
                              "checkpoint_id": parent_id}}
            if parent_id
            else None
        )

        return CheckpointTuple(
            config={"configurable": {"thread_id": thread, "checkpoint_ns": ns,
                                     "checkpoint_id": checkpoint_id}},
            checkpoint=stored["checkpoint"],
            metadata=stored["metadata"],
            parent_config=parent_config,
            pending_writes=self._pending_writes(thread, ns, checkpoint_id),
        )

    def _pending_writes(
        self, thread: str, ns: str, checkpoint_id: str,
    ) -> list[tuple[str, str, Any]]:
        raw = self.client.get(self._writes_key(thread, ns, checkpoint_id))
        if not raw:
            return []
        return [
            (w["task_id"], w["channel"], self._unpack(w["value"]))
            for w in json.loads(_text(raw) or "[]")
        ]

    def list(
        self,
        config: dict[str, Any] | None,
        *,
        filter: dict[str, Any] | None = None,  # noqa: A002 — имя из контракта LangGraph
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """
        История снимков ветки, от свежего к старому.

        Идентификаторы снимков LangGraph выдаёт UUID6 — они упорядочены по
        времени, поэтому лексикографическая сортировка совпадает с
        хронологической. На UUID4 это было бы неверно, и история приходила бы
        в случайном порядке.
        """
        if config is None:
            return
        thread, ns, _ = self._ids(config)

        prefix = f"{_CP}{thread}:{ns}:"
        ids = sorted(
            (_text(k) or "")[len(prefix):]
            for k in self.client.scan_iter(match=f"{prefix}*")
        )
        ids.reverse()

        before_id = (before or {}).get("configurable", {}).get("checkpoint_id")
        produced = 0
        for checkpoint_id in ids:
            if before_id and checkpoint_id >= before_id:
                continue
            item = self.get_tuple(
                {"configurable": {"thread_id": thread, "checkpoint_ns": ns,
                                  "checkpoint_id": checkpoint_id}}
            )
            if item is None:
                continue
            if filter and not all(item.metadata.get(k) == v for k, v in filter.items()):
                continue
            yield item
            produced += 1
            if limit is not None and produced >= limit:
                return

    def delete_thread(self, thread_id: str) -> None:
        """Убрать все снимки прогона. Зовётся при удалении задачи арендатором."""
        for pattern in (f"{_CP}{thread_id}:", f"{_WRITES}{thread_id}:", f"{_LATEST}{thread_id}:"):
            keys = [_text(k) for k in self.client.scan_iter(match=f"{pattern}*")]
            if keys:
                self.client.delete(*[k for k in keys if k])
