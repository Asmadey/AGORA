"""
Задача, наполняющая исчезнувший набор, обязана останавливаться.

─── Что случилось 18.09.2026 ────────────────────────────────────────────────
Генерация ста персон шла двадцать семь минут, звала модель и не записала
ничего. Её набор удалили из интерфейса уже после старта: `deletePersonaSets`
отказывал только наборам, на которых стоит прогон, а состояние «сейчас
генерируется» не было защищено ничем.

Воркер этого не заметил. Проверка существования делается один раз, на старте
задачи, и она рабочая — следующая задача в очереди упала за 0,066 секунды с
внятным «слепок корпуса не найден». Но та, что уже стартовала, писала прогресс
через `UPDATE … WHERE id = …` и не смотрела `rowcount`: ноль затронутых строк
неотличим от успеха ни для psycopg, ни для celery.

Наружу расхождение вышло единственным доступным ему способом — соседний прогон
необъяснимо стоял в очереди за задачей-зомби.

Отсюда два теста: ноль строк на обновлении прогресса означает «набора больше
нет» и обязан остановить задачу, а непустое обновление обязано пройти молча.
Прогресс пишется раз в `PROGRESS_EVERY` персон, и эта же запись служит
периодической перепроверкой — отдельный SELECT для того же ответа был бы вторым
походом в базу за тем, что уже известно.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.persona.tasks import (  # noqa: E402
    PROGRESS_EVERY,
    PersonaSetGone,
    _progress_reporter,
)

SET_ID = "9cb08349-90a1-457a-8dec-54655131c5d7"
TENANT = "11111111-1111-1111-1111-111111111111"


def test_zero_rows_stops_the_task() -> None:
    """Набор удалили — платить за оставшиеся персоны не за что."""
    calls: list[tuple] = []

    def vanished(tenant_id: str, sql: str, params: tuple) -> int:
        calls.append(params)
        return 0

    report = _progress_reporter(TENANT, SET_ID, update=vanished)

    with pytest.raises(PersonaSetGone) as caught:
        report(PROGRESS_EVERY, 100)

    assert SET_ID in str(caught.value), "в причине обязан стоять набор, иначе её нечем читать"
    assert len(calls) == 1


def test_written_progress_passes_quietly() -> None:
    written: list[int] = []

    def alive(tenant_id: str, sql: str, params: tuple) -> int:
        written.append(params[0])
        return 1

    report = _progress_reporter(TENANT, SET_ID, update=alive)
    report(PROGRESS_EVERY, 100)
    assert written == [PROGRESS_EVERY]


def test_between_checkpoints_the_base_is_not_touched() -> None:
    """Раз в PROGRESS_EVERY персон, а не на каждой: см. комментарий к константе."""
    touched: list[int] = []

    def alive(tenant_id: str, sql: str, params: tuple) -> int:
        touched.append(params[0])
        return 1

    report = _progress_reporter(TENANT, SET_ID, update=alive)
    for done in range(1, PROGRESS_EVERY):
        report(done, 100)
    assert touched == []
