"""
Вердикт первой попытки сохраняется рядом с финальным.

─── Зачем ────────────────────────────────────────────────────────────────────
На боевом наборе из 60 персон **30 не прошли проверку связности с первого раза**,
трое не прошли вовсе. Это две трети расхода на сборку аудитории: каждое
пересоздание — новая генерация, новое обогащение и новая проверка.

Установить, ЗА ЧТО бракуют, по сохранённым данным было нельзя. `validate_set`
подменял вердикт вердиктом замены, и в базу попадал только последний — то есть
вердикт УЖЕ ПРОШЕДШЕЙ персоны. Претензия, из-за которой предыдущую выбросили,
исчезала вместе с ней.

Первый же взгляд на уцелевшие тексты дал гипотезу: проверяющая модель засчитывает
за расхождение «атрибут отсутствует в тексте портрета», хотя в том же вердикте
сама пишет «отсутствие упоминания не является расхождением». Проверить её нечем,
пока первый вердикт не сохраняется.

─── Почему рядом, а не вместо ────────────────────────────────────────────────
Финальный вердикт описывает персону, которая ЛЕЖИТ в наборе, и по нему её читают.
Первый описывает ту, которой в наборе нет. Подменить одно другим значило бы
получить в карточке претензии не к той персоне.
"""

from __future__ import annotations

from typing import Any

from agent_core.persona.validate import validate_set

PERSONA = {"id": "p1", "name": "Наталья", "narrative": "любит документальное"}


class Judge:
    """Судья-заглушка: отдаёт заготовленные вердикты по очереди."""

    def __init__(self, verdicts: list[dict[str, Any]]):
        self.verdicts = list(verdicts)
        self.seen = 0

    def complete(self, *, prompt: str) -> str:  # noqa: ARG002
        import json

        self.seen += 1
        payload = self.verdicts.pop(0) if self.verdicts else {"consistent": True, "issues": []}
        return json.dumps(payload, ensure_ascii=False)


#: Уверенность выше MIN_CONFIDENCE: вердикт «несвязна» с меньшей отклоняется самим
#: валидатором и пересоздания не вызывает — на этом первая редакция теста и
#: споткнулась, получив «прошла с первого раза» там, где ждала отбраковку.
REJECT = {"consistent": False, "confidence": 0.95, "issues": ["атрибут children не упомянут"]}
ACCEPT = {"consistent": True, "confidence": 0.95, "issues": []}


def _run(verdicts: list[dict[str, Any]], replacement: dict[str, Any] | None = None):
    return validate_set(
        [dict(PERSONA)],
        client=Judge(verdicts),
        regenerate=lambda index, attempt: replacement,  # noqa: ARG005
        template="проверь {{persona_dna}} и {{narrative}}",
    )


def test_first_verdict_is_kept_when_persona_was_replaced():
    outcome = _run([REJECT, ACCEPT], replacement={"id": "p2", "name": "Мария"})
    verdict = outcome.verdicts[0]

    assert verdict.consistent is True, "финальный вердикт — про ту персону, что осталась"
    assert verdict.first is not None, "вердикт первой попытки потерян"
    assert verdict.first.consistent is False
    assert "children" in " ".join(verdict.first.issues)


def test_without_replacement_there_is_no_first_verdict():
    """
    Персона прошла с первого раза — второго вердикта нет, и выдумывать его нельзя.

    Пустой `first` у прошедшей персоны отличает «не браковали» от «браковали и
    забыли записать»; без этого различия статистика отбраковок недостоверна.
    """
    outcome = _run([ACCEPT])
    assert outcome.verdicts[0].first is None


def test_first_verdict_survives_several_attempts():
    """
    Попыток может быть несколько. Сохраняется САМАЯ ПЕРВАЯ: она про исходную
    персону, а промежуточные — про замены, которых в наборе тоже не осталось.
    """
    outcome = _run(
        [REJECT, {"consistent": False, "confidence": 0.95, "issues": ["вторая претензия"]}, ACCEPT],
        replacement={"id": "p2", "name": "Мария"},
    )
    verdict = outcome.verdicts[0]
    assert verdict.first is not None
    assert "children" in " ".join(verdict.first.issues), "сохранён не первый вердикт"


def test_first_verdict_is_serialisable_for_storage():
    """В базу уходит словарь: вложенный вердикт обязан пережить сериализацию."""
    import json

    outcome = _run([REJECT, ACCEPT], replacement={"id": "p2", "name": "Мария"})
    payload = outcome.verdicts[0].to_json()

    text = json.dumps(payload, ensure_ascii=False)
    assert "initial" in payload, "первый вердикт не попал в то, что пишется в базу"
    assert payload["initial"]["consistent"] is False
    assert json.loads(text)["initial"]["issues"]
