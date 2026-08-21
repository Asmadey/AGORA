"""
Пересборка расшифровки готового прогона другим движком.

─── Зачем ────────────────────────────────────────────────────────────────────
Прогон 0051 расшифрован parakeet: 59 % покрытия речи и «Сот мальчишек» вместо
«Семьсот мальчишек». Пересчитывать его целиком — это час на разбор кадров и
двадцать вызовов модели на персон, при том что меняется одна вещь: текст речи.

Джоба перезапускает ТОЛЬКО распознавание и пересобирает пакет материала тем же
`build_pack`, каким его собирает конвейер. Не своей раскладкой: вторая
реализация группировки реплик по сценам разошлась бы с первой молча, и таймлайн
после пересборки перестал бы совпадать с таймлайном настоящего прогона.

─── Чего джоба НЕ делает и почему это важно ──────────────────────────────────
Отчёт, ответы персон и вердикты судьи остаются прежними: они посчитаны по
СТАРОМУ тексту. После пересборки экран показывает речь, которой персоны не
видели. Это осознанная асимметрия — владелец просил показать новую расшифровку
на готовом прогоне, — и она обязана быть обратимой: прежний пакет сохраняется
целиком.

─── Про диаризацию ───────────────────────────────────────────────────────────
Заново её не гоняем: pyannote на пятидесяти минутах — это час работы, а
говорящие от смены движка ASR не меняются. Разметка восстанавливается из старых
реплик пакета, у каждой из которых уже проставлен `speaker`.
"""

from __future__ import annotations

from agent_core.maintenance.retranscribe import rebuild_pack, speakers_from_lines

OLD_LINES = [
    {"start": 10.0, "end": 14.0, "text": "Чисть и достоинство", "speaker": "SPEAKER_00"},
    {"start": 15.0, "end": 19.0, "text": "Темсот мальчишек", "speaker": "SPEAKER_01"},
    {"start": 40.0, "end": 44.0, "text": "Где уборки", "speaker": None},
]

SCENES = [
    {"timestamp_sec": 0.0, "end_sec": 30.0, "panel_index": 0, "scene_description": "госпиталь"},
    {"timestamp_sec": 30.0, "end_sec": 60.0, "panel_index": 1, "scene_description": "переулок"},
]

PACK = {
    "title": "Константинополь",
    "duration_sec": 60.0,
    "scenes": SCENES,
    "transcript": OLD_LINES,
    "stitched": True,
}


class Engine:
    """Движок-заглушка: отдаёт заданные реплики и запоминает, о чём его спросили."""

    def __init__(self, segments):
        self.segments = segments
        self.asked: list[str] = []

    def __call__(self, audio, model=None, **_):
        self.asked.append(str(audio))
        return self.segments


class Segment:
    def __init__(self, start, end, text):
        self.start, self.end, self.text = start, end, text


def test_speakers_are_restored_from_old_lines():
    """
    Разметка говорящих переживает смену движка: она про голоса, а не про слова.
    """
    turns = speakers_from_lines(OLD_LINES)
    assert {t["speaker"] for t in turns} == {"SPEAKER_00", "SPEAKER_01"}
    assert all("start" in t and "end" in t for t in turns)


def test_lines_without_a_speaker_are_not_invented():
    """Реплика без говорящего не должна порождать выдуманного участника."""
    turns = speakers_from_lines([{"start": 1.0, "end": 2.0, "text": "а", "speaker": None}])
    assert turns == []


def test_new_text_replaces_the_old_one():
    engine = Engine([
        Segment(10.0, 14.0, "Честь и достоинство"),
        Segment(15.0, 19.0, "Семьсот мальчишек втоптали землю"),
    ])
    pack = rebuild_pack(PACK, audio="/tmp/a.wav", model="gigaam-v3-e2e-rnnt", engine=engine)

    texts = [ln["text"] for ln in pack["transcript"]]
    assert texts == ["Честь и достоинство", "Семьсот мальчишек втоптали землю"]
    assert engine.asked == ["/tmp/a.wav"]


def test_scenes_survive_untouched():
    """
    Разбор кадров стоит дорого и к речи отношения не имеет. Потерять его при
    пересборке значит превратить дешёвую джобу в полный прогон.
    """
    engine = Engine([Segment(10.0, 14.0, "Честь и достоинство")])
    pack = rebuild_pack(PACK, audio="/tmp/a.wav", model="m", engine=engine)

    assert len(pack["scenes"]) == len(SCENES)
    assert pack["scenes"][0]["scene_description"] == "госпиталь"
    assert pack["title"] == "Константинополь"
    assert pack["duration_sec"] == 60.0


def test_timeline_is_rebuilt_and_carries_the_new_lines():
    """Экран читает `timeline[].lines`, а не сырой транскрипт."""
    engine = Engine([Segment(10.0, 14.0, "Честь и достоинство")])
    pack = rebuild_pack(PACK, audio="/tmp/a.wav", model="m", engine=engine)

    said = [ln["text"] for cell in pack["timeline"] for ln in cell.get("lines", [])]
    assert said == ["Честь и достоинство"]


def test_speaker_labels_carry_over_to_the_new_lines():
    engine = Engine([Segment(10.5, 13.5, "Честь и достоинство")])
    pack = rebuild_pack(PACK, audio="/tmp/a.wav", model="m", engine=engine)
    assert pack["transcript"][0]["speaker"] == "SPEAKER_00"


def test_empty_result_does_not_wipe_the_pack():
    """
    Движок промолчал — это отказ, а не «речи нет».

    Без этой проверки сбой распознавания стирал бы расшифровку готового прогона
    начисто, и восстановить её было бы неоткуда.
    """
    engine = Engine([])
    try:
        rebuild_pack(PACK, audio="/tmp/a.wav", model="m", engine=engine)
    except ValueError as exc:
        assert "пуст" in str(exc).lower()
    else:
        raise AssertionError("пустая расшифровка молча затёрла пакет")
