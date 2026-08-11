"""
Детерминированные правила QA — задача #19.

Здесь живёт всё, для чего модель не нужна. Разделение не про экономию вызовов,
хотя и про неё тоже: у двух слоёв разная природа отказа, и смешивать их значит
терять оба свойства сразу.

Правило либо сработало, либо нет, и повторный прогон даст тот же ответ. Ролик
длится сто секунд, ссылка ведёт на 07:45 — это арифметика, и подтверждать её
мнением модели незачем. Судья же отвечает по-разному на один и тот же вход, и
проверять им арифметику значит вносить шум туда, где его не было.

Отсюда порядок слоёв, который держит `run.py`: сначала правила, судья — только
по тем ответам, где правила ничего не нашли. Обратный порядок означал бы, что
арифметически доказанный дефект можно замять мнением модели, и что за каждый
такой ответ мы ещё и платим.

─── Чего правила НЕ ловят ─────────────────────────────────────────────────────
Согласованность ответа с характером персоны. Пацифист, восхищённый сценой
насилия, проходит все проверки этого модуля: баллы в диапазоне, таймкоды на
месте, анкета покрыта. Это работа судьи, и `run_qa` обязан сказать в `degraded`,
когда судьи не было, — иначе «правила прошли» прочитается как «QA прошёл».
"""

from __future__ import annotations

import re
from typing import Any

#: Допуск к длительности ролика. Секунда, а не ноль: таймкод последней сцены
#: округляется при склейке, и ссылка на 01:40 при длительности 99.6 с — это
#: округление, а не выдумка. Ноль допуска дал бы флаг на каждом ответе,
#: сославшемся на финал, и метрика qa_catches_injected покраснела бы на
#: правильных ответах.
TIMECODE_TOLERANCE_SEC = 1.0

#: Разрыв между общим впечатлением и готовностью рекомендовать, после которого
#: ответ считается противоречивым. Пять баллов из десяти — это «понравилось на
#: девять, но посоветую на три»: не редкая позиция, а несходящаяся.
SCORE_NPS_MAX_GAP = 5

#: Баллы, при которых оценка и намерение досмотреть обязаны согласовываться.
#: Середина шкалы (4–7) намеренно оставлена свободной: «на шесть, но выключил
#: бы» — обычная зрительская позиция, и флаг на ней был бы ложным.
HIGH_SCORE = 8
LOW_SCORE = 3

#: Доли просмотра, при которых ответ обязан согласовываться с намерением. Как и
#: с баллами, середина оставлена свободной: «досмотрел бы, но бросил на
#: половине» — реальная позиция зрителя, а не дефект.
HIGH_WATCHED_SHARE = 80
LOW_WATCHED_SHARE = 20

_SCORE_FIELDS = ("overall_impression", "plot", "acting", "music", "cinematography")

#: Таймкод вида M:SS, MM:SS или H:MM:SS. Секунды ограничены 0–59 намеренно:
#: без этого «10:75» и любая пара чисел через двоеточие читались бы как время.
#: Границы (?<![\d:]) и (?![\d:]) не дают развалить H:MM:SS на два таймкода.
_TIMECODE = re.compile(r"(?<![\d:])(\d{1,2}):([0-5]\d)(?::([0-5]\d))?(?![\d:])")

#: Слова, по которым распознаётся намерение прекратить просмотр. Список нужен
#: потому, что формулировка приходит из трёх мест сразу: из промпта респондента
#: («скорее выключить»), из корпуса («Скорее хотелось остановить просмотр») и от
#: модели, которая перескажет своими словами. Сверять с закрытым перечнем
#: значило бы ловить не противоречие, а несовпадение формулировки.
_STOP_MARKERS = ("выключ", "останов", "прекрат", "бросил", "не досм", "не стал смотреть")
_CONTINUE_MARKERS = ("досмотр", "до конца", "продолж", "не отрыва")


def _watched_share_reasons(perception: dict[str, Any], stance: str) -> list[str]:
    """
    Доля просмотра против намерения досмотреть.

    Поле необязательное: оно есть только в анкетах с вопросом о доле просмотра,
    и его отсутствие — законный случай, а не дефект. Зато присутствующее поле
    обязано согласовываться с `retention_intent`: это две формулировки одного
    факта, и расхождение между ними означает, что одна из них выдумана.

    Проверка вне шкалы важнее, чем кажется. Промпт требует проценты, но модель
    охотно отдаёт долю единицей, и 0.9 вместо 90 занижает средний досмотр на
    порядок — при этом отчёт выглядит совершенно правдоподобно.
    """
    raw = perception.get("watched_share_pct")
    if raw is None:
        return []

    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return [f"watched_share_pct не число: {raw!r}"]

    # Дробное значение проверяется до приведения к int, а не после. `int(0.9)`
    # даёт ноль, то есть ровно тот дефект, который тут ловится: доля от единицы
    # вместо процентов превращается в правдоподобный «не смотрел вообще».
    if float(raw) != int(raw):
        return [
            f"watched_share_pct={raw!r} дробное: ожидаются целые проценты 0–100, "
            f"а не доля от единицы"
        ]

    share = int(raw)
    if not 0 <= share <= 100:
        return [f"watched_share_pct={share} вне шкалы 0–100 (ожидаются проценты)"]

    if share >= HIGH_WATCHED_SHARE and stance == "stop":
        return [
            f"доля просмотра {share}% при намерении прекратить просмотр "
            f"({perception.get('retention_intent')!r})"
        ]
    if share <= LOW_WATCHED_SHARE and stance == "continue":
        return [
            f"доля просмотра {share}% при намерении досмотреть "
            f"({perception.get('retention_intent')!r})"
        ]
    return []


def timecodes(text: str) -> list[float]:
    """Все таймкоды в тексте, в секундах. Пустой список — их там нет."""
    out: list[float] = []
    for first, second, third in _TIMECODE.findall(text or ""):
        if third:
            out.append(int(first) * 3600 + int(second) * 60 + int(third))
        else:
            out.append(int(first) * 60 + int(second))
    return out


def retention_stance(value: Any) -> str:
    """
    Намерение досмотреть: ``continue`` | ``stop`` | ``unknown``.

    Отрицание проверяется первым: «не досмотрел бы» содержит и «досмотр», и
    «не досм», и порядок проверок здесь решает, в какую сторону будет ошибка.
    """
    text = str(value or "").lower()
    if not text:
        return "unknown"
    if any(m in text for m in _STOP_MARKERS):
        return "stop"
    if any(m in text for m in _CONTINUE_MARKERS):
        return "continue"
    return "unknown"


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def consistency_reasons(answer: dict[str, Any], survey: dict[str, Any] | None = None) -> list[str]:
    """
    Внутренние противоречия ответа. Пустой список — правила ничего не нашли.

    Слово «внутренние» здесь существенно: все проверки смотрят только внутрь
    одного ответа и не заглядывают ни в профиль персоны, ни в материал. Такой
    дефект не зависит ни от ролика, ни от того, кто отвечал, и потому ловится
    без модели.
    """
    reasons: list[str] = []
    scores = answer.get("scores") if isinstance(answer.get("scores"), dict) else {}
    perception = answer.get("perception") if isinstance(answer.get("perception"), dict) else {}

    for field in _SCORE_FIELDS:
        value = _int_or_none(scores.get(field))
        if scores.get(field) is not None and value is None:
            reasons.append(f"балл {field} не число: {scores.get(field)!r}")
        elif value is not None and not 1 <= value <= 10:
            reasons.append(f"балл {field}={value} вне шкалы 1–10")

    nps = _int_or_none(perception.get("recommendation_nps_1_to_10"))
    if perception.get("recommendation_nps_1_to_10") is not None and nps is None:
        reasons.append("NPS не число")
    elif nps is not None and not 1 <= nps <= 10:
        reasons.append(f"NPS={nps} вне шкалы 1–10")

    overall = _int_or_none(scores.get("overall_impression"))
    stance = retention_stance(perception.get("retention_intent"))

    if overall is not None and 1 <= overall <= 10:
        if overall >= HIGH_SCORE and stance == "stop":
            reasons.append(
                f"впечатление {overall}/10 при намерении прекратить просмотр "
                f"({perception.get('retention_intent')!r})"
            )
        if overall <= LOW_SCORE and stance == "continue":
            reasons.append(
                f"впечатление {overall}/10 при намерении досмотреть "
                f"({perception.get('retention_intent')!r})"
            )
        if nps is not None and 1 <= nps <= 10 and abs(overall - nps) >= SCORE_NPS_MAX_GAP:
            reasons.append(f"впечатление {overall}/10 против рекомендации {nps}/10")

    reasons.extend(_watched_share_reasons(perception, stance))

    verbatims = answer.get("verbatims") if isinstance(answer.get("verbatims"), dict) else {}
    if not any(str(v).strip() for v in verbatims.values()):
        reasons.append("вербатимы пусты: обоснования оценок нет")

    questions = (survey or {}).get("questions") or []
    asked = {str(q.get("id")) for q in questions if isinstance(q, dict) and q.get("id")}
    if asked:
        given = answer.get("survey_answers")
        given_keys = set(map(str, given)) if isinstance(given, dict) else set()
        missing = sorted(asked - given_keys)
        if missing:
            reasons.append(f"анкета покрыта не полностью, нет ответов: {', '.join(missing)}")

    return reasons


def grounding_reasons(answer: dict[str, Any], pack: dict[str, Any] | None = None) -> list[str]:
    """
    Ссылки на то, чего в материале не было. Пустой список — правила чисты.

    Проверяются и `grounding_refs`, и вербатимы: выдуманный таймкод чаще всего
    появляется именно в тексте («на седьмой минуте меня зацепило»), а поле
    refs персона заполняет аккуратнее — там оно у неё на виду.
    """
    reasons: list[str] = []
    refs = answer.get("grounding_refs")
    refs = [str(r) for r in refs] if isinstance(refs, list) else []
    if not [r for r in refs if r.strip()]:
        reasons.append("нет ни одной отсылки к материалу (grounding_refs пуст)")

    duration = (pack or {}).get("duration_sec")
    if not isinstance(duration, (int, float)) or duration <= 0:
        # Длительности нет — сравнивать не с чем. Молчим намеренно: флаг
        # «таймкод не проверен» на каждом ответе научил бы не читать флаги.
        return reasons

    limit = float(duration) + TIMECODE_TOLERANCE_SEC
    verbatims = answer.get("verbatims") if isinstance(answer.get("verbatims"), dict) else {}
    sources = [("grounding_refs", r) for r in refs]
    sources += [(f"вербатим {k}", str(v)) for k, v in verbatims.items()]

    for where, text in sources:
        for seconds in timecodes(text):
            if seconds > limit:
                reasons.append(
                    f"{where}: таймкод {_hhmmss(seconds)} за пределами ролика "
                    f"({_hhmmss(float(duration))})"
                )
    return reasons


def _hhmmss(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 60:02d}:{total % 60:02d}" if total < 3600 else (
        f"{total // 3600:d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
    )
