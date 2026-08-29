"""
Прогон, чей воркер умер, обязан перестать быть RUNNING.

─── Что случилось ───────────────────────────────────────────────────────────
28.08.2026 четыре конвейера пошли одновременно, и воркера убило по памяти:
`WorkerLostError: Worker exited prematurely: signal 9 (SIGKILL)`. Три строки
`tasks` остались в статусе RUNNING навсегда.

Навсегда — не оборот речи. Статус ставит сам конвейер, из блока `except` в
`pipeline/tasks.py`; SIGKILL исключения не возбуждает, процесс просто исчезает,
и выполнить `_set_task_status` некому. Строку не переведёт в FAILED ни Celery
(задача для него уже потеряна), ни веб (он только читает), ни следующий прогон.

Видно это было так: экран показывает «идёт», `DELETE` отвечает 202 «отмена
запрошена» и не удаляет — удалить можно только остановленный, — и цикл
замыкается. Прогон нельзя ни доиграть, ни убрать.

─── Почему решение вынесено в чистую функцию ────────────────────────────────
Вопрос «жив ли прогон» — это арифметика над тремя величинами: возрастом,
временем последнего события и потолками Celery. Проверять её живой базой значит
не проверять вовсе: чтобы получить осиротевший прогон, надо убить воркера.
"""

from __future__ import annotations

import time

import pytest

from agent_core.maintenance.reaper import (
    HARD_LIMIT_SEC,
    HEARTBEAT_GRACE_SEC,
    OrphanVerdict,
    is_orphan,
)


def _run(status="RUNNING", age_sec=60.0, last_event_age_sec=10.0):
    now = time.time()
    return {
        "status": status,
        "started_at": now - age_sec,
        "last_event_at": None if last_event_age_sec is None else now - last_event_age_sec,
        "now": now,
    }


class TestЖивойПрогонНеТрогается:
    def test_только_что_запущенный_жив(self):
        v = is_orphan(**_run(age_sec=5, last_event_age_sec=5))
        assert v.orphaned is False

    def test_долгий_но_отчитывающийся_жив(self):
        # Два с половиной часа — законно: потолок конвейера три часа. Пока
        # события идут, прогон работает, и трогать его нельзя: осиротевшим
        # объявят живой прогон, а пользователь увидит FAILED на работающем.
        v = is_orphan(**_run(age_sec=2.5 * 3600, last_event_age_sec=30))
        assert v.orphaned is False

    def test_узел_молчит_меньше_отсрочки(self):
        # Разбор кадров и распознавание речи идут долго и между событиями
        # молчат. Отсрочка должна это переживать.
        v = is_orphan(**_run(last_event_age_sec=HEARTBEAT_GRACE_SEC - 60))
        assert v.orphaned is False

    @pytest.mark.parametrize("status", ["QUEUED", "REPORT_READY", "FAILED", "CANCELLED"])
    def test_не_идущий_прогон_не_осиротевший(self, status):
        # QUEUED ждёт воркера — это законно и не ограничено потолком задачи.
        # Завершённые статусы трогать не за чем.
        v = is_orphan(**_run(status=status, age_sec=10 * 3600, last_event_age_sec=10 * 3600))
        assert v.orphaned is False


class TestМёртвыйПрогонЛовится:
    def test_молчание_дольше_отсрочки(self):
        v = is_orphan(**_run(age_sec=3600, last_event_age_sec=HEARTBEAT_GRACE_SEC + 60))
        assert v.orphaned is True
        assert "не подавал признаков" in v.reason

    def test_старше_жёсткого_потолка_даже_если_отчитывался(self):
        # Celery убивает задачу на TIME_LIMIT. Прогон старше потолка не может
        # идти — что бы ни лежало в снимке прогресса.
        v = is_orphan(**_run(age_sec=HARD_LIMIT_SEC + 60, last_event_age_sec=5))
        assert v.orphaned is True
        assert "жёсткого потолка" in v.reason

    def test_снимка_нет_вовсе(self):
        # Снимок в Valkey живёт сутки. Его отсутствие у идущего прогона значит,
        # что событий не было очень давно, — считаем от старта.
        v = is_orphan(**_run(age_sec=HEARTBEAT_GRACE_SEC + 60, last_event_age_sec=None))
        assert v.orphaned is True

    def test_снимка_нет_но_прогон_молод(self):
        # Между постановкой и первым событием проходит время: воркер тянет
        # образ, поднимает модели. Молодой прогон без снимка — не сирота.
        v = is_orphan(**_run(age_sec=30, last_event_age_sec=None))
        assert v.orphaned is False


class TestПричинаГодитсяДляЭкрана:
    def test_причина_называет_числа(self):
        v = is_orphan(**_run(age_sec=4 * 3600, last_event_age_sec=None))
        assert v.orphaned
        # Пользователь увидит эту строку в поле `error` вместо молчания.
        # «Прогон осиротел» без чисел не отличить от любого другого отказа.
        assert any(ch.isdigit() for ch in v.reason), v.reason
        assert len(v.reason) > 40, "причина слишком коротка, чтобы что-то объяснить"

    def test_живой_прогон_причины_не_имеет(self):
        assert is_orphan(**_run()).reason == ""


class TestКонтракт:
    def test_потолок_согласован_с_celery(self):
        # Жёсткий потолок сборщика обязан быть НЕ МЕНЬШЕ потолка задачи, иначе
        # сборщик объявит осиротевшим прогон, который Celery ещё считает живым.
        #
        # Значение читается из окружения в обоих модулях; тест сверяет их между
        # собой там, где celery установлен, — то есть в образе воркера и в CI.
        celery_app = pytest.importorskip(
            "agent_core.celery_app", reason="celery не установлен — сверка идёт в образе воркера"
        )
        assert HARD_LIMIT_SEC >= celery_app.TIME_LIMIT_SEC, (
            "сборщик убьёт прогон раньше, чем это сделает Celery"
        )

    def test_вердикт_неизменяем(self):
        # frozen-датакласс: вердикт уезжает в `tasks.error` и в журнал, и
        # правка его на полпути сделала бы причину в базе и причину в логе
        # разными.
        v = OrphanVerdict(orphaned=False, reason="")
        with pytest.raises(AttributeError):
            v.orphaned = True  # type: ignore[misc]


class TestСборщикПодключён:
    """
    Механизм без провода — самый частый дефект этого проекта.

    Портреты были построены и не читались конвейером, анкета собиралась и не
    доезжала до прогона, счётчик переспроса считался и не попадал в отчёт.
    Каждый раз обе стороны были написаны и протестированы порознь.

    Сборщик отличается тем, что его молчание НЕОТЛИЧИМО от исправной работы:
    «сирот нет» и «сборщик не запускается» дают одинаково пустой экран.
    """

    def test_задача_celery_объявлена(self):
        celery_app = pytest.importorskip("agent_core.celery_app")
        assert "agora.reap_orphans" in celery_app.app.tasks, (
            "задача не зарегистрирована — расписание будет ссылаться в пустоту"
        )

    def test_расписание_содержит_сборщик(self):
        celery_app = pytest.importorskip("agent_core.celery_app")
        schedule = celery_app.app.conf.beat_schedule or {}
        entries = [e for e in schedule.values() if e.get("task") == "agora.reap_orphans"]
        assert entries, f"в расписании нет сборщика: {sorted(schedule)}"
        assert entries[0]["schedule"] > 0

    def test_планировщик_поднимается_вместе_с_воркером(self):
        # Расписание в конфиге ничего не запускает само: нужен процесс beat.
        # Здесь он встроен в воркер флагом --beat, и это единственное место, где
        # видно, что планировщик вообще существует.
        from pathlib import Path

        compose = Path(__file__).resolve().parents[3] / "infra" / "docker-compose.yml"
        text = compose.read_text("utf-8")
        assert "--beat" in text, (
            "воркер запускается без планировщика — расписание не сработает ни разу"
        )

    def test_обход_требует_подключения(self):
        # Без DATABASE_URL уборка обязана сказать об этом, а не вернуть пустой
        # список: пустой список читается как «сирот нет».
        import os

        from agent_core.maintenance.reaper import sweep

        saved = os.environ.pop("DATABASE_URL", None)
        try:
            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                sweep(apply=False)
        finally:
            if saved is not None:
                os.environ["DATABASE_URL"] = saved
