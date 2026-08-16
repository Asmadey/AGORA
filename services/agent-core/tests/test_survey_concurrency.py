"""
Персоны внутри пачки опрашиваются одновременно.

─── Что показал замер ───────────────────────────────────────────────────────
После того как расшифровка и диаризация поехали параллельно (473 с → 274 с),
узкое место переехало:

    transcribe_and_diarize  274 с
    evaluate_personas       366 с   ← теперь главное
    analyze_chunks           15 с
    qa                       58 с

Двенадцать персон опрашивались по очереди, при том что каждая независима:
её срез собирается из собственной DNA, материала и анкеты, и ответы друг на
друга не влияют — это записано в модульном докстринге `respondent/run.py` как
условие изоляции.

Пачки по пять из PRD §8 уже были, но означали только «единицу прогресса и
отказоустойчивости»: цикл внутри пачки шёл последовательно.

─── Почему это безопасно для изоляции ───────────────────────────────────────
Изоляция здесь структурная, а не по договорённости: `build_slice` — чистая
функция, она ничего не хранит между вызовами и ничего не меняет во входных
объектах. Именно поэтому её можно звать из нескольких потоков сразу, ничего не
меняя в устройстве: общего изменяемого состояния, в котором могли бы смешаться
две персоны, попросту нет.

Обращения к провайдеру — сетевые, поэтому потоки дают полное перекрытие: GIL
отпускается на время ожидания ответа.

─── Что проверяется ─────────────────────────────────────────────────────────
Не «стало быстрее» — это свойство сети. Проверяется то, что зависит от кода:
внутри пачки запросы действительно пересекаются во времени, порядок ответов
остаётся детерминированным, отказ одной персоны не уносит остальных, а размер
пачки продолжает ограничивать число одновременных обращений — иначе пятьсот
персон ушли бы к провайдеру разом и получили бы 429.
"""

from __future__ import annotations

import json
import threading
import time

from agent_core.respondent.run import BATCH_SIZE, run_survey

PACK = {"title": "Ролик", "timeline": [{"time": "0:00–0:05", "scene": "заставка"}]}

ANSWER = json.dumps({
    "scores": {"overall_impression": 7, "plot": 6, "acting": 7, "music": 5,
               "cinematography": 6},
    "perception": {"interest_level": "скорее интересен", "emotions_evoked": ["интерес"],
                   "idea_comprehension": "понятно", "realism_perception": "реалистичные",
                   "retention_intent": "скорее досмотреть", "watched_share_pct": 60,
                   "recommendation_nps_1_to_10": 7},
    "survey_answers": {},
    "verbatims": {"why_impression": "цепляет"},
    "grounding_refs": ["0:00–0:05"],
}, ensure_ascii=False)


def personas(n: int) -> list[dict]:
    return [
        {"id": f"p{i}", "name": f"Персона {i}",
         # Метка в narrative — единственный способ отличить персон в
         # system-промпте: идентификатор и имя туда не подставляются, в шаблон
         # уходит только DNA.
         "dna": {"demographics": {"age_group": "25-34"},
                 "narrative": f"смотрит сериалы, метка {i}"}}
        for i in range(n)
    ]


class Concurrent:
    """Считает, сколько запросов было в полёте одновременно."""

    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.lock = threading.Lock()
        self.in_flight = 0
        self.peak = 0
        self.seen: list[str] = []

    def complete(self, *, system: str, user: str) -> str:  # noqa: ARG002
        with self.lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        try:
            time.sleep(self.delay)
            return ANSWER
        finally:
            with self.lock:
                self.in_flight -= 1


def test_requests_inside_a_batch_overlap():
    """
    Пять запросов пачки летят одновременно, а не один за другим.

    Проверяется пик одновременных обращений, а не время: время зависит от сети,
    пик — от кода.
    """
    client = Concurrent()
    run_survey(
        personas=personas(BATCH_SIZE), pack=PACK, survey=[], client=client,
        system_template="Ты — зритель.", user_template="Материал: {{video_understanding}}",
    )

    assert client.peak > 1, "запросы шли по очереди"
    assert client.peak <= BATCH_SIZE


def test_batch_size_still_bounds_concurrency():
    """
    Размер пачки остаётся потолком одновременных обращений.

    Без него пятьсот персон ушли бы к провайдеру разом: это 429 на большей части
    и оплаченные повторы. Пачка из PRD §8 была единицей прогресса и
    отказоустойчивости — теперь она ещё и потолок нагрузки.
    """
    client = Concurrent(delay=0.05)
    run_survey(
        personas=personas(BATCH_SIZE * 3), pack=PACK, survey=[], client=client,
        system_template="Ты — зритель.", user_template="Материал: {{video_understanding}}",
    )

    assert client.peak <= BATCH_SIZE, f"в полёте было {client.peak} запросов"


def test_answer_order_is_deterministic():
    """
    Порядок ответов не зависит от того, кто ответил первым.

    Иначе два прогона на одних входах давали бы разный порядок карточек, и
    сравнить их построчно было бы нельзя — а сравнение прогонов и есть смысл
    перезапуска исследования (#30).
    """
    class Jittery:
        def __init__(self):
            self.calls = 0
            self.lock = threading.Lock()

        def complete(self, *, system: str, user: str) -> str:  # noqa: ARG002
            with self.lock:
                self.calls += 1
                n = self.calls
            # Первые отвечают позже последних: порядок завершения обратный.
            time.sleep(0.05 * (BATCH_SIZE - n % BATCH_SIZE))
            return ANSWER

    outcome = run_survey(
        personas=personas(BATCH_SIZE), pack=PACK, survey=[], client=Jittery(),
        system_template="Ты — зритель.", user_template="Материал: {{video_understanding}}",
    )

    assert [a["persona_id"] for a in outcome.answers] == [f"p{i}" for i in range(BATCH_SIZE)]


def test_one_failure_does_not_take_the_batch_down():
    """
    Отказ одной персоны — минус один ответ, а не минус пачка.

    Свойство было у последовательного цикла, и перевод на потоки не повод его
    терять: ответ одной персоны — независимое наблюдение, и ронять четверых
    ради пятого значит терять оплаченное.
    """
    class OneBad:
        def complete(self, *, system: str, user: str) -> str:  # noqa: ARG002
            if "метка 2" in system:
                raise TimeoutError("провайдер молчит")
            return ANSWER

    outcome = run_survey(
        personas=personas(BATCH_SIZE), pack=PACK, survey=[], client=OneBad(),
        system_template="Ты — {{persona_dna}}",
        user_template="Материал: {{video_understanding}}",
    )

    assert outcome.failures == 1
    assert len(outcome.answers) == BATCH_SIZE - 1
    assert any("p2" in reason for reason in outcome.failure_reasons)
