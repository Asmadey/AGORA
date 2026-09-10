"""
Ответ чата: формат, разбор, признак опоры.

─── Почему не «только JSON», как в остальных промптах ───────────────────────
Владелец выбрал поток по словам. Потоковый JSON человеку показывать нельзя: он
увидел бы растущие фигурные скобки, а собрать из них текст можно только целиком
— то есть потока не было бы вовсе.

Поэтому формат ответа: **сначала проза, потом метаблок за разделителем**. Проза
стримится как есть, метаблок отсекается здесь и в ленту не попадает.

─── Опора проверяется ПОСЛЕ показа, и это осознанно ─────────────────────────
`has_support` нельзя применить до отрисовки: к моменту, когда ответ дописан, он
уже на экране. Убирать показанный текст нельзя — исчезающий ответ читается как
поломка, а не как проверка. Поэтому сообщение помечается: «без опоры на
материал».

Пометка не косметика. Весь продукт держится на том, что утверждение сопровождено
таймкодом или цитатой (`analytics/report.py`), и чат, отвечающий без опоры,
возвращает ровно то, ради отказа от чего он и написан, — правдоподобный текст.

─── «Данных нет» — не то же самое, что «без опоры» ──────────────────────────
Честное «в этом исследовании это не измерялось» опоры не имеет и иметь не может.
Считать его неопорным значит ругать модель за единственно верный ответ.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..analytics.report import has_support

#: Разделитель между прозой и метаблоком. Строка нарочно непохожа на текст,
#: который модель напишет сама: разделитель, встречающийся в ответе, обрезал бы
#: ответ на середине.
META_SEPARATOR = "\n---META---\n"


@dataclass(frozen=True)
class ChatReply:
    """Разобранный ответ. Неизменяем: он уезжает и в ленту, и в базу."""

    answer: str
    grounded: bool
    insufficient_data: bool = False
    out_of_profile: bool = False
    contradicts_previous: bool = False
    citations: tuple[dict[str, Any], ...] = ()


def split_stream_tail(raw: str) -> tuple[str, dict[str, Any]]:
    """
    Разделяет ответ на прозу и метаданные.

    Отсутствие метаблока — не отказ: проза уже показана пользователю, и
    выбрасывать её нельзя. Пустые метаданные означают «модель не отчиталась», и
    ответ в этом случае считается неопорным — так честнее, чем считать опорным.
    """
    head, sep, tail = raw.partition(META_SEPARATOR)
    if not sep:
        return raw, {}
    try:
        meta = json.loads(tail.strip())
    except json.JSONDecodeError:
        return head.rstrip(), {}
    return head.rstrip(), meta if isinstance(meta, dict) else {}


def parse_reply(raw: str) -> ChatReply:
    """Полный разбор ответа модели: проза, флаги, признак опоры."""
    answer, meta = split_stream_tail(raw)

    insufficient = bool(meta.get("insufficient_data"))
    raw_citations = meta.get("citations")
    citations = (
        tuple(c for c in raw_citations if isinstance(c, dict))
        if isinstance(raw_citations, list)
        else ()
    )

    # Опора: таймкод или цитата в тексте — та же функция, что отсеивает
    # утверждения в отчёте. Явно перечисленные ссылки засчитываются тоже:
    # модель вправе вынести их в метаблок вместо текста.
    grounded = insufficient or has_support(answer) or bool(citations)

    return ChatReply(
        answer=answer,
        grounded=grounded,
        insufficient_data=insufficient,
        out_of_profile=bool(meta.get("out_of_profile")),
        contradicts_previous=bool(meta.get("contradicts_previous")),
        citations=citations,
    )
