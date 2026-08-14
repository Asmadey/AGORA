"""
Таймлайн стоит на границах сцен, а не на расстоянии до следующей.

─── Что было ────────────────────────────────────────────────────────────────
У сцены не было конца — только момент. Поэтому ячейка таймлайна кончалась там,
где начиналась следующая сцена, а последняя — на длительности ролика. Пока
сцены идут подряд, это то же самое; расходится оно ровно в двух случаях, и оба
штатные:

· панель не собралась (ffmpeg не отдал ни одного кадра) — сцена пропускается, и
  её время молча достаётся предыдущей. Персона видит описание, растянутое на
  чужой кусок материала, и ссылается на него как на факт;
· разбор оборван капом вызовов — хвост ролика приписывается последней
  разобранной сцене, то есть отчёт по половине материала выглядит как отчёт по
  всему.

Теперь конец сцены приезжает из самой сцены. Расстояние до соседа осталось
запасным вариантом для прогонов, начатых до перехода на сцены: у них конца нет,
и выдумывать его нельзя.

─── Про слова ───────────────────────────────────────────────────────────────
`stats.words` нужен экрану исследования: «Слов» рядом со «Спикерами». Считается
по репликам таймлайна, а не по сырому транскрипту, — то есть по тому, что
персона действительно увидела.
"""

from __future__ import annotations

from agent_core.content.pack import build_pack

TRANSCRIPT = [
    {"start": 0.5, "end": 3.0, "text": "Здравствуйте, начнём с главного"},
    {"start": 6.0, "end": 9.0, "text": "Вот первый слайд"},
    {"start": 32.0, "end": 36.0, "text": "А это уже совсем другая тема"},
]
SPEAKERS = [
    {"start": 0.0, "end": 20.0, "speaker": "SPEAKER_00"},
    {"start": 20.0, "end": 40.0, "speaker": "SPEAKER_01"},
]


def _scene(index: int, start: float, end: float, **extra: object) -> dict:
    return {
        "panel_index": index,
        "timestamp_sec": start,
        "end_sec": end,
        "is_cut": True,
        "scene_description": f"сцена {index}",
        "mood": "нейтральное",
        **extra,
    }


def test_cell_ends_where_its_scene_ends():
    """
    Между сценами бывает пропуск, и он обязан остаться пропуском.

    Здесь сцена 5–20 не собралась. Ячейка первой сцены обязана кончиться на 5,
    а не растянуться до 20: описание «сцена 0» относится к первым пяти секундам
    и ни к чему больше.
    """
    pack = build_pack(
        transcript=TRANSCRIPT,
        speakers=SPEAKERS,
        scenes=[_scene(0, 0.0, 5.0), _scene(1, 20.0, 40.0)],
        duration_sec=40.0,
        mode="short",
        title="t",
    )
    cells = [(c["start"], c["end"]) for c in pack.full()["timeline"]]

    assert (0.0, 5.0) in cells, cells
    assert (0.0, 20.0) not in cells, cells


def test_scene_without_end_falls_back_to_the_next_one():
    """
    Прогоны до перехода на сцены несут только начало. Конец им не выдумывается:
    ячейка тянется до следующей сцены — прежнее поведение, честное для тех
    данных.
    """
    old = {"panel_index": 0, "timestamp_sec": 0.0, "scene_description": "старая"}
    older = {"panel_index": 1, "timestamp_sec": 10.0, "scene_description": "старая 2"}

    pack = build_pack(
        transcript=TRANSCRIPT, speakers=SPEAKERS, scenes=[old, older],
        duration_sec=40.0, mode="short", title="t",
    )
    cells = [(c["start"], c["end"]) for c in pack.full()["timeline"]]

    assert cells[0] == (0.0, 10.0), cells


def test_scene_end_beyond_duration_is_clamped():
    """
    Конец за длительностью подрезается, а не выбрасывает сцену.

    Начало из-за границ означает выдумку модели и сцену отбрасывает. Конец
    ставим мы сами, из сетки, и превысить длительность он может только
    округлением — выбрасывать из-за миллисекунды разобранную сцену незачем.
    """
    pack = build_pack(
        transcript=[], speakers=[], scenes=[_scene(0, 0.0, 40.6)],
        duration_sec=40.0, mode="short", title="t",
    )
    assert pack.full()["scenes"][0]["end_sec"] == 40.0
    assert pack.full()["dropped_scenes"] == []


def test_cell_carries_the_cut_flag():
    """
    По `is_cut` экран отличает монтажную склейку от разреза длинной сцены.

    Без флага таймлайн рисовал бы смену сцены там, где спикер просто продолжает
    говорить, — то есть показывал бы монтаж, которого в материале нет.
    """
    pack = build_pack(
        transcript=[], speakers=[],
        scenes=[_scene(0, 0.0, 30.0), _scene(1, 30.0, 60.0, is_cut=False)],
        duration_sec=60.0, mode="short", title="t",
    )
    assert [c["is_cut"] for c in pack.full()["timeline"]] == [True, False]


def test_stats_count_words_and_speakers():
    """«Слов» и «Спикеров» — показатели экрана исследования."""
    pack = build_pack(
        transcript=TRANSCRIPT, speakers=SPEAKERS,
        scenes=[_scene(0, 0.0, 20.0), _scene(1, 20.0, 40.0)],
        duration_sec=40.0, mode="short", title="t",
    )
    stats = pack.full()["stats"]

    assert stats["speakers"] == 2
    # 4 + 3 + 6 слов по репликам таймлайна.
    assert stats["words"] == 13, stats
