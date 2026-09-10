"""
Чат по результатам исследования (#28): сборка среза и разбор ответа.

─── Что здесь на самом деле проверяется ─────────────────────────────────────
Не «чат отвечает» — это работа модели, и утверждать о ней нечего. Проверяется
то, что решает КОД:

* какие данные персона видит, а какие не видит физически;
* что ответ без опоры на материал помечен, а не выдан за обоснованный;
* что «в исследовании этого нет» отличается от «модель промолчала».

─── Почему изоляция проверяется тем же приёмом, что в #18 ───────────────────
Не «в ответе нет чужих имён» — это проверка вывода, и она зелёная ровно до
первого совпадения формулировок. Проверяется ВХОД: в срезе персоны чужих
ответов нет как данных. Одна и та же проверка в двух формах разошлась бы, и
разошлась бы молча.
"""

from __future__ import annotations

import json

import pytest

from agent_core.chat.agent import (
    META_SEPARATOR,
    ChatReply,
    parse_reply,
    split_stream_tail,
)
from agent_core.chat.context import analyst_context, persona_context

PACK = {
    "title": "Ролик",
    "scenes": [{"start": 0, "end": 12, "description": "заставка"}],
}
SURVEY = [{"id": "q1", "label": "Общее впечатление", "type": "scale"}]
REPORT = {"aggregate": {"overall_impression": 7.2}, "narrative": ["Понравилось"]}

ANNA = {"id": "p-anna", "name": "Анна", "dna": {"demographics": {"age_group": "25-34"}}}
BORIS = {"id": "p-boris", "name": "Борис", "dna": {"demographics": {"age_group": "45-59"}}}

ANSWERS = [
    {"persona_id": "p-anna", "scores": {"overall_impression": 8},
     "verbatim": "Мне зашло, особенно музыка на 00:12"},
    {"persona_id": "p-boris", "scores": {"overall_impression": 4},
     "verbatim": "Скучно, выключил бы на второй минуте"},
]


class TestИзоляцияПерсоны:
    def test_в_срез_не_попадают_чужие_ответы(self):
        ctx = persona_context(
            persona=ANNA, pack=PACK, survey=SURVEY, answers=ANSWERS, history=[]
        )
        blob = json.dumps(ctx, ensure_ascii=False)
        assert "Борис" not in blob
        assert "p-boris" not in blob
        assert "Скучно" not in blob, "чужой вербатим доехал до среза персоны"

    def test_свои_ответы_в_срезе_есть(self):
        # Обратная сторона: срез без собственных ответов делает «допрос»
        # разговором с персоной, которая не помнит, что отвечала.
        ctx = persona_context(
            persona=ANNA, pack=PACK, survey=SURVEY, answers=ANSWERS, history=[]
        )
        assert "Мне зашло" in json.dumps(ctx, ensure_ascii=False)

    def test_персона_не_знает_об_отчёте(self):
        # Она зритель, а не участник исследования: агрегат, темы и чужие оценки
        # ей знать неоткуда, и знание сделало бы ответ подстройкой под итог.
        ctx = persona_context(
            persona=ANNA, pack=PACK, survey=SURVEY, answers=ANSWERS, history=[]
        )
        assert "aggregate" not in json.dumps(ctx, ensure_ascii=False)

    def test_срез_не_меняет_входные_объекты(self):
        # Тот же приём, что в build_slice: изоляция — не проверка на выходе, а
        # отсутствие места, где чужие данные могли бы задержаться.
        before = json.dumps(ANSWERS, ensure_ascii=False, sort_keys=True)
        persona_context(persona=ANNA, pack=PACK, survey=SURVEY, answers=ANSWERS, history=[])
        assert json.dumps(ANSWERS, ensure_ascii=False, sort_keys=True) == before


class TestСрезАналитика:
    def test_аналитик_видит_всех_персон_этого_прогона(self):
        ctx = analyst_context(
            report=REPORT, pack=PACK, survey=SURVEY, answers=ANSWERS, qa_flags=[], history=[]
        )
        blob = json.dumps(ctx, ensure_ascii=False)
        assert "Мне зашло" in blob and "Скучно" in blob

    def test_аналитик_видит_отчёт(self):
        ctx = analyst_context(
            report=REPORT, pack=PACK, survey=SURVEY, answers=ANSWERS, qa_flags=[], history=[]
        )
        assert "aggregate" in json.dumps(ctx, ensure_ascii=False)


class TestРазборОтвета:
    def test_проза_отделяется_от_метаблока(self):
        raw = f"Сегмент 45+ оценил ниже.{META_SEPARATOR}" + json.dumps(
            {"citations": [], "insufficient_data": False}, ensure_ascii=False
        )
        prose, meta = split_stream_tail(raw)
        assert prose.strip() == "Сегмент 45+ оценил ниже."
        assert meta["insufficient_data"] is False

    def test_метаблока_нет_вовсе(self):
        # Модель может не дописать хвост. Это не отказ: проза уже показана
        # пользователю, и выбрасывать её нельзя. Метаданные при этом пусты, и
        # ответ считается неопорным — так честнее, чем считать его опорным.
        prose, meta = split_stream_tail("Просто текст без хвоста")
        assert prose == "Просто текст без хвоста"
        assert meta == {}

    def test_битый_метаблок_не_роняет_разбор(self):
        prose, meta = split_stream_tail(f"Текст{META_SEPARATOR}{{не json")
        assert prose == "Текст"
        assert meta == {}


class TestОпораОтвета:
    def test_ответ_с_таймкодом_опорный(self):
        reply = parse_reply(f"На 00:12 играет музыка.{META_SEPARATOR}{{}}")
        assert reply.grounded is True

    def test_ответ_без_опоры_помечен(self):
        # Проза уже показана — поток. Убрать её нельзя, поэтому помечаем.
        reply = parse_reply(f"Аудитории в целом понравилось.{META_SEPARATOR}{{}}")
        assert reply.grounded is False
        assert reply.answer  # текст сохраняется, а не стирается

    def test_нехватку_данных_видно_отдельно(self):
        # «В исследовании это не измерялось» — законный ответ, и он не должен
        # выглядеть как неопорный: помечать его «без опоры» значит ругать
        # модель за честность.
        raw = f"Это не измерялось.{META_SEPARATOR}" + json.dumps({"insufficient_data": True})
        reply = parse_reply(raw)
        assert reply.insufficient_data is True
        assert reply.grounded is True, "честное «данных нет» не считается неопорным"

    def test_флаги_персоны_доезжают(self):
        raw = f"Не думал об этом.{META_SEPARATOR}" + json.dumps(
            {"out_of_profile": True, "contradicts_previous": False}
        )
        reply = parse_reply(raw)
        assert reply.out_of_profile is True
        assert reply.contradicts_previous is False

    def test_ответ_неизменяем(self):
        reply = ChatReply(answer="a", grounded=True)
        with pytest.raises(AttributeError):
            reply.answer = "b"  # type: ignore[misc]


class TestКонтрактПромптов:
    def test_оба_промпта_просят_метаблок(self):
        # Формат ответа сменился с «только JSON» на «проза, потом метаблок»:
        # потоковый JSON человеку показывать нельзя. Промпт, оставшийся в старом
        # формате, дал бы поток из фигурных скобок.
        from pathlib import Path

        prompts = Path(__file__).resolve().parents[3] / "prompts"
        for name in ("chat.analyst.md", "chat.persona_followup.md"):
            text = (prompts / name).read_text("utf-8")
            assert META_SEPARATOR in text, f"{name} не описывает разделитель метаблока"
            assert "Только JSON" not in text, f"{name} всё ещё требует чистый JSON"
