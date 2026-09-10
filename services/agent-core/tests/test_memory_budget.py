"""
Бюджет памяти воркера: сколько процессов помещается в машину.

─── Что этот тест удерживает ────────────────────────────────────────────────
10.09.2026 на боевом нашлось `WORKER_CONCURRENCY=4` при умолчании `1` в
compose. Умолчание там не случайное: рядом лежит замер 04.08.2026 — 5,4 ГБ на
процесс с моделями, — и вывод, что четыре копии в 11,6 ГБ не помещаются.

Не рвануло только потому, что прогоны запускались по одному. Два одновременных
положили бы воркер посреди работы, и выглядело бы это случайным сбоем.

Удерживал умолчание КОММЕНТАРИЙ. §5 CLAUDE.md прямо требует падающую проверку
вместо комментария — вот она.

─── Почему проверяется запущенная команда, а не конфиг ──────────────────────
Файл compose выглядел исправным: `--concurrency=${WORKER_CONCURRENCY:-1}`.
Значение приезжало из `.env.local`, которого нет ни в одном дифф-обзоре.
Проверка, читающая объявленное умолчание, прошла бы зелёной при живом дефекте.

Поэтому разбор идёт по строке команды РАБОТАЮЩЕГО процесса.
"""
from __future__ import annotations

import pytest

from agent_core.maintenance.memory_budget import (
    PER_PROCESS_GB,
    RESERVED_GB,
    budget,
    max_concurrency,
    parse_concurrency,
    read_total_gb,
)

#: Фактическая боевая машина, замерено 10.09.2026.
LIVE_GB = 11.67

#: Спецификация PRD §14.
SPEC_GB = 16.0


class TestАрифметика:
    def test_один_процесс_помещается_в_боевую_машину(self):
        assert budget(concurrency=1, total_gb=LIVE_GB).fits

    def test_два_процесса_уже_не_помещаются(self):
        assert not budget(concurrency=2, total_gb=LIVE_GB).fits

    def test_боевое_нарушение_поймано(self):
        # Ровно то, что стояло на сервере до 10.09.2026.
        v = budget(concurrency=4, total_gb=LIVE_GB)
        assert not v.fits
        assert v.need_gb > v.have_gb

    def test_формула_воспроизводит_умолчание_compose(self):
        # Сильная проверка самой формулы: она обязана независимо прийти к тому
        # же числу, которое человек вывел замером 04.08.2026 и записал
        # умолчанием. Разойдись они — неверна формула либо умолчание.
        assert max_concurrency(LIVE_GB) == 1

    def test_машина_по_спецификации_допускает_больше(self):
        assert max_concurrency(SPEC_GB) >= 2

    def test_крошечная_машина_даёт_ноль_а_не_отрицание(self):
        assert max_concurrency(2.0) == 0

    def test_причина_называет_числа(self):
        # «Не помещается» без чисел заставляет считать заново руками, а на
        # боевом это делают в спешке.
        v = budget(concurrency=4, total_gb=LIVE_GB)
        assert "4" in v.reason
        assert str(int(v.have_gb)) in v.reason or f"{v.have_gb:.1f}" in v.reason

    def test_замеры_названы_и_не_нулевые(self):
        assert PER_PROCESS_GB > 0 and RESERVED_GB > 0


class TestРазборЗапущеннойКоманды:
    def test_флаг_через_равно(self):
        cmd = "celery -A agent_core.celery_app worker --loglevel=info --concurrency=4 --beat"
        assert parse_concurrency(cmd) == 4

    def test_флаг_через_пробел(self):
        assert parse_concurrency("celery worker --concurrency 3") == 3

    def test_короткая_форма(self):
        assert parse_concurrency("celery worker -c 2 --beat") == 2

    def test_отсутствие_флага_это_неизвестность_а_не_единица(self):
        # Без флага celery берёт число ядер. На 8 vCPU это восемь процессов —
        # худший случай из возможных. Считать отсутствие флага единицей значило
        # бы объявить безопасным самое опасное состояние.
        assert parse_concurrency("celery -A agent_core.celery_app worker --beat") is None

    def test_чужое_слово_не_путается_с_флагом(self):
        assert parse_concurrency("celery worker --pool=prefork --autoscale=4,1") is None

    def test_мусор_не_роняет_разбор(self):
        assert parse_concurrency("celery worker --concurrency=") is None
        assert parse_concurrency("") is None


class TestЧтениеПамяти:
    def test_cgroup_v2_с_потолком(self, tmp_path):
        (tmp_path / "memory.max").write_text("8589934592\n")  # 8 ГиБ
        assert read_total_gb(cgroup_dir=tmp_path) == pytest.approx(8.0, abs=0.01)

    def test_cgroup_без_потолка_уходит_к_meminfo(self, tmp_path):
        (tmp_path / "memory.max").write_text("max\n")
        meminfo = tmp_path / "meminfo"
        meminfo.write_text("MemTotal:       12241234 kB\nMemFree: 100 kB\n")
        got = read_total_gb(cgroup_dir=tmp_path, meminfo=meminfo)
        assert got == pytest.approx(11.67, abs=0.05)

    def test_ничего_не_прочиталось_это_None_а_не_ноль(self, tmp_path):
        # Ноль объявил бы негодной любую машину. Неизвестность обязана
        # оставаться неизвестностью.
        assert read_total_gb(cgroup_dir=tmp_path, meminfo=tmp_path / "нет") is None
