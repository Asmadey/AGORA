"""
Обогащение персон сообщает, сколько уже сделано.

─── Зачем ───────────────────────────────────────────────────────────────────
Генерация аудитории — единственная операция продукта, у которой нет никакой
обратной связи. Скелеты персон собираются за миллисекунды, а обогащение —
последовательный цикл: один вызов модели на персону, таймаут 60 секунд на
каждый. Шестьдесят персон не помещаются даже в таймаут маршрута (120 секунд),
и пользователь видит крутящийся спиннер, который однажды превращается в
ошибку, — при том что половина персон уже была написана и оплачена.

Обратный вызов — минимум, который делает прогресс возможным. Сам показ «40/60»
живёт выше, но взять число неоткуда, пока цикл молчит.

─── Почему отказ обратного вызова не роняет генерацию ───────────────────────
Прогресс — служебная информация. Уронить из-за неё аудиторию, которая уже
наполовину написана моделью, значит поменять оплаченный результат на аккуратную
отчётность.
"""

from __future__ import annotations

from agent_core.persona.enrich import enrich_personas


class FakeClient:
    """Отдаёт достаточно длинный narrative, чтобы он прошёл проверку длины."""

    def __init__(self):
        self.calls = 0

    def complete(self, *, prompt: str) -> str:  # noqa: ARG002
        self.calls += 1
        return (
            "Живёт в областном центре, работает посменно, вечерами смотрит сериалы "
            "с телефона и раздражается на затянутые сцены. Считает, что хорошая "
            "история должна цеплять в первые пять минут, иначе переключает."
        ) * 2


def personas(n: int) -> list[dict]:
    return [
        {
            "id": f"p{i}",
            "name": f"Персона {i}",
            "narrative": "скелет",
            "demographics": {
                "age": 30,
                "gender": "жен",
                "city": "Казань",
                "geo": "центры субъектов",
            },
            "lifestyle_and_interests": {"work_status": "работает", "hobbies": ["сериалы"]},
            "psychographics_and_values": {"important_values": ["Семья"]},
        }
        for i in range(n)
    ]


def test_progress_is_reported_for_every_persona():
    """Каждая персона отзывается ровно один раз, и счёт идёт от одного до N."""
    seen: list[tuple[int, int]] = []
    result = enrich_personas(
        personas(4),
        client=FakeClient(),
        prompt="{{skeleton_json}} {{min_len}}",
        on_progress=lambda done, total: seen.append((done, total)),
    )
    assert len(result.personas) == 4
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)], seen


def test_progress_is_optional():
    """
    Без обратного вызова поведение прежнее.

    Обогащение зовут и из CLI, и из тестов; обязательный аргумент сломал бы
    все эти места ради одного нового свойства.
    """
    result = enrich_personas(
        personas(2), client=FakeClient(), prompt="{{skeleton_json}} {{min_len}}"
    )
    assert len(result.personas) == 2


def test_broken_callback_does_not_lose_the_audience():
    """
    Отказ обратного вызова не роняет генерацию.

    Прогресс — служебная информация. Уронить из-за неё аудиторию, которая уже
    наполовину написана моделью, значит поменять оплаченный результат на
    аккуратную отчётность.
    """

    def explode(done: int, total: int) -> None:  # noqa: ARG001
        raise RuntimeError("канал прогресса недоступен")

    result = enrich_personas(
        personas(3),
        client=FakeClient(),
        prompt="{{skeleton_json}} {{min_len}}",
        on_progress=explode,
    )
    assert len(result.personas) == 3, "персоны потеряны из-за прогресса"
