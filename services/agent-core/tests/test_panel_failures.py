"""
Отказ на одной панели не отменяет разбор ролика.

─── Как это нашлось ─────────────────────────────────────────────────────────
Первый же golden-сет после перехода на сценную сетку упал дважды подряд:

    analyze_chunks → openai.OpenAIError: Error code: 400
    {'code': 'data_inspection_failed',
     'message': 'Input data may contain inappropriate content'}

Провайдер отказался разбирать ОДНУ панель — модерация входа сочла кадр
неподобающим. Прогон при этом уже оплатил скачивание, прокси, извлечение звука,
транскрипцию и часть панелей, и всё это выбросил.

Дефект существовал и раньше, просто редко срабатывал: до сценной сетки на
трёхминутном ролике было шесть панелей, стало два десятка — и вероятность
задеть модерацию выросла вчетверо. Смена единицы разбора не создала дефект, она
сделала его обычным.

─── Почему деградация, а не отказ ───────────────────────────────────────────
Ровно тот же выбор уже сделан для опроса персон: ответ одной персоны —
независимое наблюдение, и ронять прогон из-за одного таймаута значит терять
четыреста девяносто девять оплаченных ответов ради пятисотого. Панель — такое же
независимое наблюдение: девятнадцать разобранных сцен полезнее, чем ноль.

Но молчать нельзя. Пропущенная сцена — это кусок материала, которого персона не
видела, и отчёт обязан сказать, сколько таких кусков и почему. Иначе «модель не
заметила финал» будет объясняться свойствами ролика, а не отказом провайдера.

─── Где граница ─────────────────────────────────────────────────────────────
Все панели отказали — это не деградация, а отказ: video_understanding пуст,
персонам показывать нечего, и отчёт получился бы по ролику, которого никто не
смотрел.
"""

from __future__ import annotations

import pytest

from agent_core.frames.analyze import AnalysisResult, analyze_panels
from agent_core.frames.extract import Panel

PROMPT = "разбери сцену {{scene_start}}–{{scene_end}}"


def panels(n: int) -> list[Panel]:
    return [
        Panel(
            index=i,
            timestamp_sec=float(i * 5),
            end_sec=float(i * 5 + 5),
            frame_times=[i * 5 + 1.0],
            image=f"panel-{i}".encode(),
        )
        for i in range(n)
    ]


class Moderated:
    """Отвергает панели с указанными индексами — как модерация провайдера."""

    def __init__(self, reject: set[int]):
        self.reject = reject
        self.calls = 0

    def analyze(self, *, image: bytes, prompt: str) -> dict:  # noqa: ARG002
        index = int(image.decode().split("-")[1])
        self.calls += 1
        if index in self.reject:
            raise RuntimeError(
                "Error code: 400 - {'code': 'data_inspection_failed', "
                "'message': 'Input data may contain inappropriate content'}"
            )
        return {"scene_description": f"сцена {index}", "mood": "нейтральное"}


def test_one_rejected_panel_does_not_kill_the_run():
    """Девятнадцать разобранных сцен полезнее, чем ноль."""
    client = Moderated({3})
    result = analyze_panels(panels(6), client=client, prompt=PROMPT)

    assert isinstance(result, AnalysisResult)
    assert len(result.scenes) == 6, "сцена должна остаться в таймлайне даже без описания"
    assert result.failures == 1
    assert client.calls == 6, "отказ на одной панели не должен прерывать обход"


def test_failed_scene_keeps_its_place_and_says_so():
    """
    У пропущенной сцены остаются её границы и признак отказа.

    Границы нужны таймлайну: без них в материале появилась бы дыра, и следующая
    сцена молча растянулась бы на чужой кусок. Признак нужен персоне и отчёту:
    выдуманное описание было бы хуже отсутствующего.
    """
    result = analyze_panels(panels(3), client=Moderated({1}), prompt=PROMPT)

    failed = result.scenes[1]
    assert failed["timestamp_sec"] == 5.0
    assert failed["end_sec"] == 10.0
    assert failed["analysis_failed"] is True
    assert "data_inspection_failed" in failed["reason"]
    assert not failed.get("scene_description"), "описания быть не должно — его не получили"


def test_reasons_are_collected_for_the_report():
    """
    Причины доезжают до отчёта, а не остаются в логе воркера.

    «Модель не заметила финал» иначе объяснялось бы свойствами ролика, а не
    отказом провайдера, — и объяснение это никто бы не опроверг: к моменту
    разбора отчёта исходное видео удалено по политике хранения.
    """
    result = analyze_panels(panels(5), client=Moderated({0, 4}), prompt=PROMPT)

    assert result.failures == 2
    assert len(result.failure_reasons) == 2
    assert all("data_inspection_failed" in reason for reason in result.failure_reasons)
    # В причине обязан быть таймкод: без него непонятно, какой кусок материала
    # выпал, а именно это и нужно знать читателю отчёта.
    assert any("0.00" in reason for reason in result.failure_reasons)


def test_all_panels_rejected_is_a_failure_not_degradation():
    """
    Ноль разобранных сцен — отказ.

    Персонам показывать нечего, и отчёт получился бы по ролику, которого никто
    не смотрел. Такой прогон обязан упасть с внятной причиной, а не выдать
    правдоподобные числа.
    """
    with pytest.raises(RuntimeError) as exc:
        analyze_panels(panels(4), client=Moderated({0, 1, 2, 3}), prompt=PROMPT)

    assert "ни одной" in str(exc.value)
    assert "data_inspection_failed" in str(exc.value)


def test_cache_is_not_poisoned_by_a_failure():
    """
    Отказ не кладётся в кэш.

    Иначе повторный прогон (#30) получил бы пустое описание из кэша, не заплатив
    ни рубля и не сделав ни одной попытки, — то есть дефект стал бы постоянным,
    причём бесплатным и потому незаметным.
    """
    from agent_core.frames.analyze import MemoryCache

    cache = MemoryCache()
    analyze_panels(panels(3), client=Moderated({1}), prompt=PROMPT, cache=cache)

    assert len(cache.store) == 2, "в кэш попали только успешные разборы"
