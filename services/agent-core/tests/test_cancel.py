"""
Прогон можно отменить, и отмена доходит до воркера между узлами.

─── Зачем понадобилось ──────────────────────────────────────────────────────
Удалить исследование в состоянии QUEUED или RUNNING было нельзя: маршрут
отвечал 409, и текст был честным — у воркера нет канала отмены. Он читает
чекпоинт и пишет прогресс; пропавшая строка задачи для него выглядит сбоем
базы, и он уходит в повтор.

Но у пользователя накопились прогоны, которые не возьмёт уже никто: воркер
перезапускался, очередь чистилась, задача осталась в QUEUED навсегда. Отказ
«дождитесь окончания» для них — обещание, которое никогда не исполнится.

Поэтому канал заводится по-настоящему, а не обходится флагом в интерфейсе.

─── Где именно проверяется отмена ───────────────────────────────────────────
Между узлами, в `_traced` — обёртке, через которую и так проходит каждый узел
графа. Внутри узла проверять нечего: узел это один вызов модели или один запуск
ffmpeg, прерывать его на середине означало бы бросать оплаченную работу и
оставлять временные файлы.

Гранулярность «между узлами» означает, что отмена срабатывает не мгновенно:
разбор кадров длится минуты. Это честная цена, и интерфейс обязан говорить
«отменяется», а не «отменено».
"""

from __future__ import annotations

import pytest

from agent_core.pipeline.graph import RunCancelled, _traced


class Recorder:
    """Считает, сколько узлов реально выполнилось."""

    def __init__(self):
        self.ran: list[str] = []

    def node(self, name: str):
        def fn(state):
            self.ran.append(name)
            return {}

        return fn


def test_node_runs_when_not_cancelled():
    """Страховка: без отмены обёртка ничего не меняет."""
    rec = Recorder()
    node = _traced("sample_frames", rec.node("sample_frames"), None, is_cancelled=lambda: False)
    node({"task_id": "t1"})
    assert rec.ran == ["sample_frames"]


def test_cancelled_run_stops_before_the_node():
    """
    Отменённый прогон не выполняет следующий узел.

    Именно «до», а не «после»: смысл отмены в том, чтобы не платить за
    следующий вызов модели, а не в том, чтобы отметить факт.
    """
    rec = Recorder()
    node = _traced("analyze_chunks", rec.node("analyze_chunks"), None, is_cancelled=lambda: True)
    with pytest.raises(RunCancelled):
        node({"task_id": "t1"})
    assert rec.ran == [], "узел выполнился, хотя прогон отменён"


def test_cancellation_is_not_a_failure():
    """
    Отмена — отдельное исключение, а не общий отказ.

    `_traced` превращает любое исключение узла в FAILED с причиной. Если бы
    отмена шла тем же путём, пользователь увидел бы «прогон упал» на то, что
    сам же и остановил, а в отчёте о прогоне осталась бы ложная ошибка.
    """
    assert not issubclass(RunCancelled, ValueError)
    rec = Recorder()
    node = _traced("qa", rec.node("qa"), None, is_cancelled=lambda: True)
    with pytest.raises(RunCancelled) as exc:
        node({"task_id": "t1"})
    assert "отмен" in str(exc.value).lower(), exc.value


def test_absent_checker_keeps_old_behaviour():
    """
    Без переданной проверки узел работает как раньше.

    Обёртка используется и в тестах, и в местах, где отмены нет вовсе;
    обязательный аргумент сломал бы их все ради одного нового свойства.
    """
    rec = Recorder()
    node = _traced("pack", rec.node("pack"), None)
    node({"task_id": "t1"})
    assert rec.ran == ["pack"]
