"""
Сборщик мусора во внешних хранилищах.

─── Почему отдельный сборщик, а не уборка на месте ──────────────────────────
`DELETE /api/tasks/{id}` убирает строку Postgres ПОСЛЕДНЕЙ и честно пишет в
ответе, что отказ внешнего хранилища удаления не отменяет. Порядок правильный:
любой обрыв оставляет мусор, а не исследование, ссылающееся на удалённые данные.

Но у правильного порядка есть цена, и она названа прямо в коде маршрута:
«строки уже нет, и возвращать ошибку значило бы предлагать повторить операцию,
которая не повторяется». Повторить действительно нечем — адреса объектов жили в
строке и в пакете материала, которых больше нет.

Поэтому повтор обязан идти С ДРУГОЙ СТОРОНЫ: не от строки к объектам, а от
объектов к строке. Ключ `tenants/<t>/runs/<task>/frames/...` несёт идентификатор
прогона в себе — этого достаточно, чтобы спросить у базы, жив ли он.

─── Чего сборщик не делает ──────────────────────────────────────────────────
Не удаляет по умолчанию. Сухой прогон — умолчание, `--apply` — явное решение,
ровно как у сборщика осиротевших прогонов и сборщика зомби.

Не трогает то, чего не понял. Ключ, который не разобрался, остаётся на месте:
догадка о чужом формате стоит дороже гигабайта.

Не трогает свежие загрузки. Ролик попадает в хранилище ДО того, как появляется
строка прогона. Сборщик без отсрочки удалял бы файл у пользователя из-под рук,
и выглядело бы это случайным сбоем загрузки.

─── Что здесь охраняется главным ────────────────────────────────────────────
Пустое множество живых прогонов НЕ означает «всё осиротело». Оно означает это
только тогда, когда таблица прочитана успешно. Не прочитана — сборщик обязан
упасть, а не убрать хранилище целиком.

Эта сессия нашла три дефекта одного вида — пустой список, прошедший за успех.
Сборщику с правами на удаление такой дефект стоил бы всех данных сразу.
"""
from __future__ import annotations

import pytest

from agent_core.maintenance.orphan_storage import (
    UPLOAD_GRACE_SEC,
    StoredObject,
    orphan_run_objects,
    orphan_snapshots,
    orphan_uploads,
    parse_run_key,
    sweep,
)

LIVE = "11111111-1111-1111-1111-111111111111"
DEAD = "22222222-2222-2222-2222-222222222222"
TENANT = "de15d1e3-e2f6-41c7-966d-91c186046066"


def _frame(task: str, n: int = 0) -> str:
    return f"tenants/{TENANT}/runs/{task}/frames/{n:09d}.jpg"


# ─── Разбор ключа ───────────────────────────────────────────────────────────


def test_ключ_прогона_разбирается_на_арендатора_и_прогон():
    assert parse_run_key(_frame(DEAD)) == (TENANT, DEAD)


@pytest.mark.parametrize(
    "key",
    [
        f"tenants/{TENANT}/uploads/{DEAD}.mp4",  # не прогон
        "runs/abc/frames/0.jpg",  # без арендатора
        f"tenants/{TENANT}/runs/не-uuid/frames/0.jpg",  # не идентификатор
        "",
    ],
)
def test_непонятый_ключ_не_разбирается(key):
    assert parse_run_key(key) is None


# ─── Кадры прогонов ─────────────────────────────────────────────────────────


def test_кадры_живого_прогона_не_трогаются():
    keys = [_frame(LIVE, 0), _frame(LIVE, 1), _frame(DEAD, 0)]
    assert orphan_run_objects(keys, live_task_ids={LIVE}) == [_frame(DEAD, 0)]


def test_непонятый_ключ_остаётся_на_месте():
    strange = "tenants/x/что-то/совсем/другое.bin"
    assert orphan_run_objects([strange], live_task_ids=set()) == []


def test_без_живых_прогонов_осиротело_всё_что_разобрано():
    keys = [_frame(DEAD, 0), _frame(DEAD, 1)]
    assert orphan_run_objects(keys, live_task_ids=set()) == keys


# ─── Загрузки ───────────────────────────────────────────────────────────────


def test_загрузка_на_которую_смотрит_прогон_не_трогается():
    key = f"tenants/{TENANT}/uploads/a.mp4"
    objs = [StoredObject(key=key, size=10, age_sec=UPLOAD_GRACE_SEC * 2)]
    assert orphan_uploads(objs, referenced={key}) == []


def test_свежая_загрузка_не_трогается_даже_без_ссылки():
    key = f"tenants/{TENANT}/uploads/b.mp4"
    objs = [StoredObject(key=key, size=10, age_sec=UPLOAD_GRACE_SEC - 1)]
    assert orphan_uploads(objs, referenced=set()) == []


def test_старая_загрузка_без_ссылки_осиротела():
    key = f"tenants/{TENANT}/uploads/c.mp4"
    objs = [StoredObject(key=key, size=10, age_sec=UPLOAD_GRACE_SEC + 1)]
    assert orphan_uploads(objs, referenced=set()) == [key]


def test_отсрочка_загрузки_щедрее_суток():
    # Ролик попадает в хранилище раньше строки прогона. Отсрочка меньше суток
    # означала бы, что сборщик вправе удалить файл у пользователя из-под рук.
    assert UPLOAD_GRACE_SEC >= 24 * 60 * 60


# ─── Слепки корпуса ─────────────────────────────────────────────────────────


def test_слепок_на_который_смотрит_набор_не_трогается():
    assert orphan_snapshots({"s1", "s2"}, referenced={"s1"}) == ["s2"]


# ─── Главная защита ─────────────────────────────────────────────────────────


def test_непрочитанная_таблица_прогонов_валит_сборщик():
    """
    None — это «не знаю», и оно не равно «живых нет».

    Разница между ними — всё хранилище. Сборщик обязан упасть здесь, а не
    принять неудачу чтения за пустую базу.
    """
    with pytest.raises(ValueError):
        orphan_run_objects([_frame(DEAD)], live_task_ids=None)

    with pytest.raises(ValueError):
        orphan_uploads([], referenced=None)

    with pytest.raises(ValueError):
        orphan_snapshots({"s1"}, referenced=None)


def test_сухой_прогон_умолчание():
    """`apply` не имеет значения по умолчанию: удаление — явное решение."""
    import inspect

    sig = inspect.signature(sweep)
    assert sig.parameters["apply"].default is False
    assert sig.parameters["apply"].kind is inspect.Parameter.KEYWORD_ONLY


# ─── Видимость прогонов ─────────────────────────────────────────────────────


def test_узкая_политика_сборщика_прогонов_валит_уборку():
    """
    Миграция 41 выдала владельцу схемы SELECT на `tasks` ТОЛЬКО со
    `status = 'RUNNING'`. Под ней `SELECT id FROM tasks` возвращает идущие
    прогоны и молчит про остальные — то есть в тихий час отвечает пустотой.

    Для сборщика осиротевших прогонов этого достаточно: он только их и ищет.
    Для сборщика хранилищ пустой ответ означал бы «живых нет» и стоил бы всех
    данных сразу: отчёты, кадры и ролики завершённых исследований.

    Отсюда проверка ДО первого чтения: видно все статусы или нет. Не видно —
    отказ, а не уборка.
    """
    from agent_core.maintenance.orphan_storage import assert_full_task_visibility

    class _Cur:
        def __init__(self, answers):
            self._answers = answers
            self._last = None

        def execute(self, sql, *args):
            self._last = sql

        def fetchone(self):
            for needle, answer in self._answers.items():
                if needle in (self._last or ""):
                    return answer
            return (None,)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Conn:
        def __init__(self, answers):
            self._answers = answers

        def cursor(self):
            return _Cur(self._answers)

    # Ни обхода RLS, ни политики — отказ.
    with pytest.raises(RuntimeError, match="видит"):
        assert_full_task_visibility(_Conn({"rolbypassrls": (False,), "pg_policies": (0,)}))

    # Политика на все строки есть — можно. Проверяется отсутствием отказа:
    # возвращать функции нечего, её работа — пропустить или не пропустить.
    assert_full_task_visibility(_Conn({"rolbypassrls": (False,), "pg_policies": (1,)}))

    # Роль обходит RLS (боевой суперпользователь) — тоже можно, и это
    # записано отдельной веткой намеренно: схема не вправе ОПИРАТЬСЯ на
    # суперпользователя, но обязана работать под ним.
    assert_full_task_visibility(_Conn({"rolbypassrls": (True,), "pg_policies": (0,)}))


# ─── Проводка в расписание ──────────────────────────────────────────────────


def test_задача_в_расписании_и_не_удаляет():
    """
    Расписание называет мусор, а не убирает его.

    Уборка сравнивает три хранилища, и цена ошибки несимметрична: молчание
    стоит гигабайтов, а ошибка в обратную сторону — кадров и отчётов живых
    исследований, восстановить которые неоткуда.

    Проверяется по исходнику, а не импортом: celery живёт в образе воркера, и
    тест обязан работать там, где его нет (§9).
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1] / "agent_core" / "celery_app.py"
    ).read_text("utf-8")

    assert '"task": "agora.sweep_storage"' in src, "задача стоит в beat_schedule"
    assert '@app.task(name="agora.sweep_storage")' in src, "задача объявлена"

    body = src[src.index('@app.task(name="agora.sweep_storage")') :]
    body = body[: body.index("@worker_ready")]
    assert "apply=False" in body, "проход по расписанию не удаляет"
    assert "apply=True" not in body, "apply=True по расписанию не допускается"


def test_миграция_42_даёт_владельцу_видеть_все_прогоны():
    """
    Без неё сборщик отказывается работать — и это правильное поведение.

    Политика 41 показывает владельцу только RUNNING. Проверка видимости
    написана так, что 41 её не удовлетворяет: у неё `qual` не пуст.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    mig = root / "infra" / "postgres" / "init" / "42_sweeper_reads_all_tasks.sql"
    assert mig.exists(), "миграция 42 заведена"

    sql = mig.read_text("utf-8")
    assert "tasks_sweeper_read" in sql
    assert "FOR SELECT" in sql, "только чтение: сборщик в tasks ничего не пишет"
    assert "USING (true)" in sql, "без ограничения по строкам — в этом смысл"
    assert "DROP POLICY IF EXISTS" in sql, "идемпотентно"
    assert "FORCE" not in sql.split("BEGIN;")[1], "FORCE не снимается"
