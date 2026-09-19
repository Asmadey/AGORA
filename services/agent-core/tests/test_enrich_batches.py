"""Наблюдаемые контракты пакетного обогащения персон."""

from __future__ import annotations

import copy
import re
import threading
import time

from agent_core.persona.enrich import MemoryCache, enrich_personas


PROMPT = "Город: {{city}}. Скелет: {{skeleton_json}}. Не короче {{min_len}}."


def make_personas(count: int) -> list[dict]:
    return [
        {
            "demographics": {
                "age": 30 + index,
                "gender": "женский",
                "city": f"Город {index}",
                "geo": "город-миллионник",
            },
            "values_and_beliefs": {"important_values": ["Семья"]},
            "narrative": "Шаблонный narrative длиной больше ста символов. " * 4,
        }
        for index in range(count)
    ]


class TimedClient:
    """Модель-заглушка с измеряемой конкуренцией и разными задержками."""

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self._lock = threading.Lock()
        self._five_call_barrier = threading.Barrier(5)

    def complete(self, *, prompt: str) -> str:
        city = int(re.search(r"Город (\d+)", prompt).group(1))
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls += 1

        try:
            # На старой последовательной реализации barrier истечёт, а тест
            # всё равно завершится и сообщит о max_active == 1, а не зависнет.
            try:
                self._five_call_barrier.wait(timeout=0.5)
            except threading.BrokenBarrierError:
                pass
            time.sleep((5 - city % 5) * 0.02)
            return f"Нарратив для города {city}. " * 12
        finally:
            with self._lock:
                self.active -= 1


def test_batch_parallelism_order_and_progress() -> None:
    """Проверяет наблюдаемую скорость, порядок результата и полный прогресс."""
    client = TimedClient()
    progress: list[tuple[int, int]] = []
    personas = make_personas(5)

    result = enrich_personas(
        personas,
        client=client,
        prompt=PROMPT,
        on_progress=lambda done, total: progress.append((done, total)),
    )

    assert client.max_active == 5, (
        f"одновременных вызовов {client.max_active}, ожидалось 5"
    )
    assert [persona["demographics"]["city"] for persona in result.personas] == [
        persona["demographics"]["city"] for persona in personas
    ]
    assert [
        int(re.search(r"города (\d+)", persona["narrative"]).group(1))
        for persona in result.personas
    ] == list(range(5))
    assert len(progress) == len(personas)


def test_duplicate_cache_keys_in_one_batch_pay_once() -> None:
    """Одинаковый ключ в одной партии не создаёт гонку и второй вызов."""
    client = TimedClient()
    cache = MemoryCache()
    first, second = make_personas(1)[0], make_personas(1)[0]

    result = enrich_personas(
        [first, second], client=client, prompt=PROMPT, cache=cache
    )

    assert client.calls == 1
    assert [persona["narrative"] for persona in result.personas] == [
        "Нарратив для города 0. " * 12
    ] * 2


def test_cache_written_by_one_batch_is_seen_by_the_next_batch() -> None:
    """Кэш читается на границе партий, а не только до всего прогона."""
    client = TimedClient()
    cache = MemoryCache()
    base = make_personas(1)[0]

    result = enrich_personas(
        [copy.deepcopy(base) for _ in range(6)], client=client, prompt=PROMPT, cache=cache
    )

    assert client.calls == 1
    assert result.cache_hits == 1
    assert len(result.personas) == 6
