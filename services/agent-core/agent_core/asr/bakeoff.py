"""
Сравнение движков распознавания без эталонного текста.

Эталона к пятидесятиминутному фильму нет и не будет: расшифровать его вручную
дороже, чем весь разбор. Но отказ, который уже случился — parakeet молчал там,
где на дорожке есть голос, — ловится без эталона, сравнением с детектором речи.

Три величины, все три считаются по одному прогону движка:

* **покрытие** — доля речи, найденной VAD, попавшая хоть в одну реплику;
* **доля кириллицы** — на русском материале английский текст означает, что
  движок ушёл не в тот язык, и это видно арифметикой, а не чтением;
* **плотность слов** — слов на минуту РЕЧИ (не на минуту файла).

Чего эти три величины не измеряют — точность. Модель, которая слышит всё и
путает окончания, по ним неотличима от идеальной. Границу стоит держать в
голове: замер отвечает на вопрос «слышит ли», а не «верно ли слышит».
"""

from __future__ import annotations

import re

#: Порог, ниже которого расшифровка считается негодной.
#:
#: Поставлен владельцем 20.08.2026: «пока покрытие речью не достигнет 95 %».
#: История величины на дорожке прогона 0051 (docs/ASR_BAKEOFF_2026-08-20.md):
#:
#:     parakeet, кусок 60 с — как шёл прогон 0051      59 %
#:     parakeet, кусок 15 с — после правки 19.08       80 %
#:     GigaAM v3-e2e-rnnt                              97 %
#:
#: Сто процентов недостижимы и не нужны: часть того, что VAD считает речью,
#: словами не является — на прогоне 0051 таких участков 35 секунд из 1237, и
#: модель молчит на них при любой длине куска.
COVERAGE_TARGET = 0.95

Span = tuple[float, float]

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def _merged(spans: list[Span]) -> list[Span]:
    """
    Отрезки без наложений.

    Две реплики на одном участке речи — это не двойное покрытие. Считать иначе
    значит поощрять движок, который дублирует куски: у parakeet на стыках чанков
    это ровно тот случай.
    """
    out: list[Span] = []
    for start, end in sorted(spans):
        if end <= start:
            continue
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def speech_seconds(speech: list[Span]) -> float:
    """Сколько всего речи нашёл детектор."""
    return round(sum(end - start for start, end in _merged(speech)), 4)


def overlap_seconds(transcript: list[Span], speech: list[Span]) -> float:
    """
    Сколько секунд речи попало в реплики.

    Реплика, лежащая вне речи, не засчитывается: это галлюцинация движка, а не
    его находка, и складывать её с полезной работой нельзя.
    """
    said = _merged(transcript)
    total = 0.0
    for s_start, s_end in _merged(speech):
        for t_start, t_end in said:
            if t_end <= s_start:
                continue
            if t_start >= s_end:
                break
            total += min(t_end, s_end) - max(t_start, s_start)
    return round(total, 4)


def coverage(transcript: list[Span], speech: list[Span]) -> float | None:
    """
    Доля речи, дошедшая до расшифровки. None — речи не найдено вовсе.

    Ноль здесь означал бы отказ движка, а немой ролик — законный случай.
    """
    total = speech_seconds(speech)
    if total <= 0:
        return None
    return round(overlap_seconds(transcript, speech) / total, 4)


def cyrillic_share(text: str) -> float | None:
    """
    Доля кириллицы среди БУКВ. None — букв нет.

    Цифры и знаки не считаются ни за кого: «в 1917 году» — русская фраза, и
    делить её долю на длину строки значило бы наказывать за даты.
    """
    letters = _LETTER.findall(text or "")
    if not letters:
        return None
    cyrillic = sum(1 for ch in letters if _CYRILLIC.match(ch))
    return round(cyrillic / len(letters), 4)


def words_per_minute(text: str, *, speech_sec: float) -> float | None:
    """
    Плотность речи. Знаменатель — секунды РЕЧИ, а не длина файла.

    Иначе фильм с получасом музыки выглядел бы вдвое хуже разговорного ролика
    при одинаковой расшифровке.
    """
    if speech_sec <= 0:
        return None
    return round(len(_WORD.findall(text or "")) * 60.0 / speech_sec, 4)


def report(
    *,
    engine: str,
    transcript: list[Span],
    text: str,
    speech: list[Span],
    seconds: float,
    peak_mb: float | None = None,
) -> dict[str, object]:
    """Одна строка сравнения — то, что кладётся рядом с такой же по другому движку."""
    total_speech = speech_seconds(speech)
    return {
        "engine": engine,
        "speech_sec": total_speech,
        "covered_sec": overlap_seconds(transcript, speech),
        "coverage": coverage(transcript, speech),
        "cyrillic": cyrillic_share(text),
        "words_per_minute": words_per_minute(text, speech_sec=total_speech),
        "segments": len(transcript),
        "wall_sec": round(seconds, 1),
        "peak_mb": peak_mb,
    }
