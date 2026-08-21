"""
Дополнительный контекст об аудитории доезжает до системного промпта персоны.

─── Что было ─────────────────────────────────────────────────────────────────
Визард умел приложить файл и запоминал его ИМЯ И РАЗМЕР. Содержимое не
читалось, наверх не уезжало и ни во что не попадало. В резюме прогона имя файла
показывалось — то есть экран утверждал, что контекст учтён.

Отличить это от работающей функции можно было только по ответам персон, а они
правдоподобны в обоих случаях.

─── Где именно шов ───────────────────────────────────────────────────────────
Между снимком настроек прогона и системным промптом. Проверяется вызовом, а не
чтением исходника: обе половины по отдельности выглядят правильными, разрыв
ровно между ними.
"""

from __future__ import annotations

from typing import Any

from agent_core.respondent.run import run_survey

PERSONAS = [{"id": "p1", "name": "Наталья", "narrative": "любит документальное"}]
PACK = {"title": "материал", "scenes": [], "transcript": []}
SURVEY: dict[str, Any] = {"questions": []}


class Recorder:
    """Клиент-заглушка: запоминает системный промпт и отдаёт разбираемый ответ."""

    def __init__(self) -> None:
        self.systems: list[str] = []

    def complete(self, *, system: str, user: str) -> str:
        self.systems.append(system)
        return (
            '{"scores": {"overall_impression": 7}, '
            '"perception": {"recommendation_nps_1_to_10": 7}, '
            '"verbatims": {"why_impression": "ок"}}'
        )


def _run(system_template: str, extra: str | None) -> Recorder:
    client = Recorder()
    run_survey(
        personas=PERSONAS,
        pack=PACK,
        survey=SURVEY,
        client=client,
        system_template=system_template,
        user_template="материал: {{video_understanding}}",
        extra_context=extra,
    )
    return client


def test_context_reaches_the_system_prompt():
    client = _run("Ты персона.", "Аудитория — подписчики нишевого канала про историю.")
    assert client.systems, "персону не спросили"
    assert "нишевого канала про историю" in client.systems[0]


def test_without_context_the_prompt_is_untouched():
    """
    Прогон без файла обязан остаться прежним побайтово.

    Иначе добавление необязательной возможности молча меняет все прежние
    прогоны, и сравнить их с новыми будет нельзя.
    """
    client = _run("Ты персона.", None)
    assert client.systems[0] == "Ты персона."


def test_empty_context_is_the_same_as_none():
    assert _run("Ты персона.", "   \n  ").systems[0] == "Ты персона."


def test_context_is_marked_as_such_not_glued_to_instructions():
    """
    Чужой текст обязан быть отделён заголовком.

    Приклеенный вплотную к инструкциям, он читается моделью как продолжение
    указаний — и файл про аудиторию начинает управлять форматом ответа.
    """
    client = _run("Ты персона.", "Аудитория — историки.")
    system = client.systems[0]
    assert system.index("Ты персона.") < system.index("Аудитория — историки.")
    assert system.count("Аудитория — историки.") == 1
    head_end = system.index("Ты персона.") + len("Ты персона.")
    between = system[head_end:system.index("Аудитория — историки.")]
    assert between.strip(), "контекст приклеен к инструкциям без разделителя"
