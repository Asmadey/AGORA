"""
Фаза 2: персона проверяется на связность со своими же атрибутами.

─── Что здесь важно ─────────────────────────────────────────────────────────
Проверка, которая зелена всегда, хуже отсутствующей: она создаёт уверенность,
не создавая гарантии. Поэтому тест начинается не с «связная проходит», а с
«несвязная НЕ проходит» — и подсаживает противоречие того самого вида, ради
которого фаза заведена: текст, опровергающий собственный атрибут.

Второе, что здесь проверяется, — граница осторожности. Недоступная модель,
неразобранный ответ и неуверенная претензия не должны выглядеть претензией к
персоне: перегенерация стоит денег, а пропущенное расхождение стоит одного
странного ответа в отчёте, который видно глазами.
"""

from __future__ import annotations

import json

from agent_core.persona.validate import (
    MAX_ATTEMPTS,
    validate_persona,
    validate_set,
)

TEMPLATE = "атрибуты: {{skeleton_json}} текст: {{narrative}} реплики: {{verbatim_pool}}"

PERSONA = {
    "id": "p1",
    "demographics": {"age_group": "25-34", "geo": "Москва"},
    "media": {"watch_frequency": "ежедневно"},
    "narrative": "Смотрит сериалы каждый вечер, живёт в Москве.",
}


class Answering:
    """Отдаёт заготовленные ответы по очереди и запоминает промпты."""

    def __init__(self, *answers: str):
        self.answers = list(answers)
        self.prompts: list[str] = []

    def complete(self, *, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else self.answers_default()

    @staticmethod
    def answers_default() -> str:
        return json.dumps({"consistent": True, "issues": [], "confidence": 0.9})


def verdict_json(consistent: bool, issues: list[str], confidence: float) -> str:
    return json.dumps(
        {"consistent": consistent, "issues": issues, "confidence": confidence},
        ensure_ascii=False,
    )


# ─── Ловит ли она то, ради чего заведена ─────────────────────────────────────


def test_contradiction_is_caught():
    """Текст, опровергающий собственный атрибут, обязан быть отвергнут."""
    client = Answering(
        verdict_json(False, ["атрибут: смотрит ежедневно; текст: не смотрит"], 0.9)
    )
    verdict = validate_persona(PERSONA, client=client, template=TEMPLATE)

    assert verdict.consistent is False
    assert verdict.checked is True
    assert any("ежедневно" in i for i in verdict.issues)


def test_clean_persona_passes():
    """Связная персона проходит без единой претензии."""
    client = Answering(verdict_json(True, [], 0.95))
    verdict = validate_persona(PERSONA, client=client, template=TEMPLATE)

    assert verdict.consistent is True
    assert verdict.issues == []


def test_prompt_gets_attributes_and_text_separately():
    """
    В промпт уезжают и атрибуты, и текст — раздельно.

    Проверяющему нужно СРАВНИТЬ их. Получив только текст, он оценивал бы
    правдоподобие рассказа, а не его связность с источником, — и это была бы
    другая проверка, с другим и бесполезным результатом.
    """
    client = Answering(verdict_json(True, [], 0.9))
    validate_persona(PERSONA, client=client, template=TEMPLATE)

    prompt = client.prompts[0]
    assert "ежедневно" in prompt, "атрибуты не доехали"
    assert "Смотрит сериалы каждый вечер" in prompt, "текст портрета не доехал"
    # narrative не должен попасть в блок атрибутов: иначе проверяющий сверяет
    # текст сам с собой и всегда находит согласие.
    skeleton = prompt.split("текст:")[0]
    assert "Смотрит сериалы каждый вечер" not in skeleton


# ─── Граница осторожности ────────────────────────────────────────────────────


def test_unavailable_model_is_not_a_complaint():
    """
    Недоступность модели — «не проверено», а не «несвязна».

    Иначе сбой сети запускал бы перегенерацию всего набора, и та не исправила
    бы ничего: причина не в персонах.
    """
    class Broken:
        def complete(self, *, prompt: str) -> str:  # noqa: ARG002
            raise TimeoutError("провайдер молчит")

    verdict = validate_persona(PERSONA, client=Broken(), template=TEMPLATE)

    assert verdict.checked is False
    assert verdict.consistent is True
    assert any("недоступен" in i for i in verdict.issues)


def test_unparsable_answer_is_not_a_complaint():
    """Ответ, который не разобрался, тоже «не проверено»."""
    verdict = validate_persona(
        PERSONA, client=Answering("конечно, давайте посмотрим"), template=TEMPLATE
    )

    assert verdict.checked is False
    assert verdict.consistent is True


def test_low_confidence_complaint_is_rejected():
    """
    Претензия без уверенности не принимается.

    Промпт велит при сомнении отвечать «связна» с низким confidence; порог —
    вторая линия на случай, если модель инструкции не послушалась.
    """
    client = Answering(verdict_json(False, ["кажется, что-то не так"], 0.2))
    verdict = validate_persona(PERSONA, client=client, template=TEMPLATE)

    assert verdict.consistent is True
    assert any("отклонена по уверенности" in i for i in verdict.issues)


def test_json_in_backticks_is_parsed():
    """```json вокруг ответа — обычное поведение чат-модели, а не сбой."""
    wrapped = "```json\n" + verdict_json(False, ["противоречие"], 0.9) + "\n```"
    verdict = validate_persona(PERSONA, client=Answering(wrapped), template=TEMPLATE)

    assert verdict.consistent is False


# ─── Пересоздание ────────────────────────────────────────────────────────────


def test_failed_persona_is_regenerated_until_it_passes():
    """Непрошедшая персона пересоздаётся, и в наборе остаётся новая."""
    client = Answering(
        verdict_json(False, ["противоречие"], 0.9),
        verdict_json(True, [], 0.9),
    )
    replacement = {**PERSONA, "id": "p1-v2", "narrative": "Исправленный портрет."}

    outcome = validate_set(
        [PERSONA],
        client=client,
        regenerate=lambda index, attempt: replacement,  # noqa: ARG005
        template=TEMPLATE,
    )

    assert outcome.regenerated == 1
    assert outcome.failed == 0
    assert outcome.personas[0]["id"] == "p1-v2"
    assert outcome.verdicts[0].attempts == 2


def test_attempts_are_bounded():
    """
    Пересоздание не бесконечно.

    Без потолка неописуемое сочетание атрибутов крутило бы генерацию до конца
    бюджета, и выглядело бы это как зависшая аудитория.
    """
    client = Answering(*[verdict_json(False, ["противоречие"], 0.9)] * 10)
    calls: list[int] = []

    outcome = validate_set(
        [PERSONA],
        client=client,
        regenerate=lambda index, attempt: (calls.append(attempt), PERSONA)[1],  # noqa: ARG005
        template=TEMPLATE,
    )

    assert outcome.verdicts[0].attempts == MAX_ATTEMPTS
    assert outcome.failed == 1
    assert len(calls) == MAX_ATTEMPTS - 1


def test_failed_persona_stays_in_the_set():
    """
    Персона, не прошедшая после всех попыток, остаётся в наборе с пометкой.

    Выбрасывать её нельзя: набор заказанного размера — это то, что оплатили и
    на чём строят выборку, а молчаливое сокращение смещает состав в сторону
    «удобных» персон, то есть ровно тех, что перестают представлять корпус.
    """
    client = Answering(*[verdict_json(False, ["противоречие"], 0.9)] * 10)

    outcome = validate_set(
        [PERSONA, PERSONA],
        client=client,
        regenerate=lambda index, attempt: None,  # noqa: ARG005
        template=TEMPLATE,
    )

    assert len(outcome.personas) == 2, "набор не должен уменьшаться"
    assert outcome.failed == 2
    assert all(v.consistent is False for v in outcome.verdicts)


def test_verdict_serialises_for_the_row():
    """Вердикт кладётся в personas.validation целиком, включая checked."""
    verdict = validate_persona(
        PERSONA, client=Answering(verdict_json(False, ["x"], 0.8)), template=TEMPLATE
    )
    payload = verdict.to_json()

    assert set(payload) == {"checked", "consistent", "issues", "confidence", "attempts"}
    # checked обязателен: «не проверялась» и «проверена, претензий нет» —
    # разные состояния, и набор, созданный до появления фазы, не должен
    # выглядеть прошедшим проверку, которой не было.
    assert payload["checked"] is True


def test_only_a_confident_contradiction_rejects_a_persona():
    """
    Порог отбраковки поднят: сомневающийся вердикт персону не заворачивает.

    ─── Почему ───────────────────────────────────────────────────────────────
    Персона — розыгрыш из распределений корпуса, а не его копия. То, что она
    вышла «немного другой», — это и есть работа генератора, а не дефект: смысл
    синтетической аудитории в том, чтобы покрыть пространство, а не повторить
    выборку. Отбраковка за непохожесть уничтожает ровно то, ради чего продукт
    существует, и делает это дорого — каждая попытка оплачена.

    Проверка остаётся, но ловит только то, ради чего заводилась: прямое
    противоречие текста своим же атрибутам. Цена ошибок несимметрична, и теперь
    порог это отражает — ложная отбраковка стоит трёх перегенераций, пропуск
    стоит одного странного портрета, который видно глазами.
    """
    from agent_core.persona import validate as v

    assert v.MIN_CONFIDENCE >= 0.8, (
        "порог ниже 0.8 заворачивает персону по неуверенному вердикту"
    )

    persona = {
        "name": "Ирина",
        "dna": {"age_group": "35-44", "geo": "центры субъектов"},
        "narrative": "портрет",
    }
    tpl = "{{skeleton_json}} {{narrative}} {{verbatim_pool}}"

    # Неуверенное «несвязна» — персона проходит.
    unsure = v.validate_persona(
        persona,
        client=Answering(json.dumps(
            {"consistent": False, "confidence": 0.6, "issues": ["сомнительно"]}
        )),
        template=tpl,
    )
    assert unsure.consistent, "неуверенный вердикт не должен заворачивать персону"

    # Уверенное «несвязна» — по-прежнему заворачивает.
    sure = v.validate_persona(
        persona,
        client=Answering(json.dumps({
            "consistent": False,
            "confidence": 0.95,
            "issues": ["в тексте «не смотрю сериалы» при ежедневном просмотре"],
        })),
        template=tpl,
    )
    assert not sure.consistent, "уверенное противоречие обязано заворачивать — иначе проверки нет"
