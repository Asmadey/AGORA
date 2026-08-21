"""
Перенос заставок: ключ кадра из пакета в `tasks.poster_ref`.

─── Почему это понадобилось ──────────────────────────────────────────────────
В списке исследований у всех прогонов стояла серая заглушка. Проверка на боевой
базе: `poster_ref` пуст У ВСЕХ, при этом все 40 пакетов в Mongo ключи кадров
содержат. Код `_save_poster` пришёл коммитом от 18.08, а ни один прогон после
него до конца не дошёл.

`tasks.poster_ref` и первая ячейка таймлайна — БУКВАЛЬНО один и тот же ключ S3,
записанный на одном шаге `_publish_frames`. Владелец сказал точно: писать новый
воркер не нужно, нужно сопряжение.

─── Почему перенос, а не чтение Mongo на лету ────────────────────────────────
Список отдаёт до ста строк; запрос за пакетом на каждую — сто обращений к Mongo
ради картинки в углу. Ради этого колонка и заводилась.
"""

from __future__ import annotations

import pytest

from agent_core.maintenance.backfill_posters import plan_backfill, poster_of

TENANT = "de15d1e3-e2f6-41c7-966d-91c186046066"


def _pack(*keys):
    return {"pack": {"scenes": [{"screenshot": k} for k in keys]}}


# ─── Выбор кадра ─────────────────────────────────────────────────────────────

def test_first_scene_with_a_frame_wins():
    assert poster_of(_pack("a.jpg", "b.jpg")) == "a.jpg"


def test_scenes_without_frames_are_skipped():
    """
    Сцена без кадра — законное состояние: разбор мог не дать панели. Заставкой
    становится первый кадр, который есть, а не первая сцена.
    """
    doc = {"pack": {"scenes": [{}, {"screenshot": None}, {"screenshot": "c.jpg"}]}}
    assert poster_of(doc) == "c.jpg"


@pytest.mark.parametrize(
    "doc",
    [{}, {"pack": {}}, {"pack": {"scenes": []}}, {"pack": {"scenes": [{}, {}]}}, None],
)
def test_no_frames_means_no_poster(doc):
    """
    Прогон, не дошедший до `stitch`, кадров не имеет физически. Подставлять ему
    чужой кадр нельзя — заглушка честнее.
    """
    assert poster_of(doc) is None


def test_garbage_in_the_pack_does_not_crash():
    # Пакеты пишутся воркером и читаются переносом много позже. Уронить перенос
    # на одной битой записи — значит не перенести и все остальные.
    doc = {"pack": {"scenes": ["строка", 42, {"screenshot": 7}, {"screenshot": "ok.jpg"}]}}
    assert poster_of(doc) == "ok.jpg"


# ─── План переноса ───────────────────────────────────────────────────────────

def test_only_tasks_without_a_poster_are_touched():
    """
    Заполненное поле не трогается: у прогона мог быть свой кадр, а перенос —
    разовая операция, которая обязана быть безопасной при повторе.
    """
    tasks = {"t1": None, "t2": "уже/есть.jpg", "t3": None}
    packs = {"t1": _pack("a.jpg"), "t2": _pack("b.jpg"), "t3": _pack("c.jpg")}

    assert plan_backfill(tasks, packs) == {"t1": "a.jpg", "t3": "c.jpg"}


def test_task_without_a_pack_is_left_alone():
    assert plan_backfill({"t1": None}, {}) == {}


def test_plan_is_empty_when_everything_is_filled():
    """Повторный запуск не делает ничего — это и есть идемпотентность."""
    assert plan_backfill({"t1": "есть.jpg"}, {"t1": _pack("a.jpg")}) == {}
