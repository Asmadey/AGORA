"""
Сборщик зомби-процессов: что он может, а чего не может никто.

─── Почему здесь нет ни одного «убить зомби» ────────────────────────────────
Зомби — уже мёртвый процесс. От него осталась строка в таблице процессов с
кодом возврата, которого не забрал родитель. Убивать там нечего: `SIGKILL` по
зомби — не операция, а обращение к покойнику.

Исчезает зомби ровно двумя способами: родитель вызывает `wait()`, либо родитель
умирает и зомби переходит к `init`, который забирает всегда.

Отсюда единственный сигнал, который этот модуль вправе послать, — `SIGCHLD`
родителю. Он безвреден по определению (действие по умолчанию — игнорировать) и
даёт родителю, у которого обработчик есть, повод дойти до `waitpid`. Если не
помогло — модуль докладывает, а решение принимает человек.

Скрипт, который шлёт `SIGKILL` по зомби, выглядит работающим и не делает
ничего. Тесты ниже держат именно эту границу.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_core.maintenance.zombies import (
    GRACE_SEC,
    Zombie,
    nudge,
    read_zombies,
    stale,
)

CLK = 100  # SC_CLK_TCK на всех наших машинах


def _proc(tmp: Path, uptime: float, procs: list[tuple[int, str, str, int, int]]) -> Path:
    """
    Собирает поддельный /proc.

    procs: (pid, comm, state, ppid, starttime_ticks)
    """
    (tmp / "uptime").write_text(f"{uptime} {uptime}\n")
    for pid, comm, state, ppid, start in procs:
        d = tmp / str(pid)
        d.mkdir()
        # Поля 5..21 конвейеру не нужны, но занимать место обязаны: starttime —
        # двадцать второе поле, и смещение считается от него.
        filler = " ".join(["0"] * 17)
        (d / "stat").write_text(f"{pid} ({comm}) {state} {ppid} {filler} {start}\n")
    return tmp


class TestРазборProc:
    def test_зомби_узнаётся_по_состоянию(self, tmp_path):
        root = _proc(tmp_path, 1000.0, [(42, "celery", "Z", 7, 0)])
        assert [z.pid for z in read_zombies(root, clock_ticks=CLK)] == [42]

    def test_живые_состояния_не_зомби(self, tmp_path):
        root = _proc(
            tmp_path,
            1000.0,
            [(1, "init", "S", 0, 0), (2, "worker", "R", 1, 0), (3, "io", "D", 1, 0)],
        )
        assert read_zombies(root, clock_ticks=CLK) == []

    def test_имя_с_пробелом_не_ломает_разбор(self, tmp_path):
        # /proc/<pid>/stat кладёт имя в скобки, и внутри бывают пробелы.
        # Наивный split() съезжает на поле, и состояние читается из имени.
        root = _proc(tmp_path, 1000.0, [(9, "Web Content", "Z", 4, 0)])
        got = read_zombies(root, clock_ticks=CLK)
        assert [(z.pid, z.ppid, z.comm) for z in got] == [(9, 4, "Web Content")]

    def test_скобка_внутри_имени_не_ломает_разбор(self, tmp_path):
        # Имя берётся до ПОСЛЕДНЕЙ скобки, иначе процесс с ')' в имени
        # разбирается со сдвигом и зомби теряется молча.
        root = _proc(tmp_path, 1000.0, [(11, "sh (old)", "Z", 4, 0)])
        got = read_zombies(root, clock_ticks=CLK)
        assert [(z.pid, z.comm) for z in got] == [(11, "sh (old)")]

    def test_возраст_считается_от_uptime(self, tmp_path):
        # uptime 1000 c, процесс стартовал на 400-й секунде → ему 600 c.
        root = _proc(tmp_path, 1000.0, [(5, "celery", "Z", 1, 400 * CLK)])
        assert read_zombies(root, clock_ticks=CLK)[0].age_sec == pytest.approx(600.0)

    def test_исчезнувший_процесс_не_роняет_обход(self, tmp_path):
        # Гонка штатная: процесс успел уйти между listdir и чтением stat.
        root = _proc(tmp_path, 1000.0, [(5, "celery", "Z", 1, 0)])
        (root / "6").mkdir()  # каталог есть, stat нет
        assert [z.pid for z in read_zombies(root, clock_ticks=CLK)] == [5]

    def test_нечисловые_каталоги_пропускаются(self, tmp_path):
        root = _proc(tmp_path, 1000.0, [(5, "celery", "Z", 1, 0)])
        (root / "self").mkdir()
        (root / "sys").mkdir()
        assert [z.pid for z in read_zombies(root, clock_ticks=CLK)] == [5]


class TestСвежийЗомбиНеТревога:
    def test_зомби_моложе_отсрочки_не_тревога(self):
        # Родитель забирает ребёнка за миллисекунды. Зомби возрастом в секунду —
        # это нормальное завершение процесса, а не дефект. Без этой отсрочки
        # проверка кричала бы на каждом здоровом выходе.
        fresh = Zombie(pid=1, ppid=2, comm="sh", age_sec=1.0)
        assert stale([fresh]) == []

    def test_зомби_старше_отсрочки_тревога(self):
        old = Zombie(pid=1, ppid=2, comm="celery", age_sec=GRACE_SEC + 1)
        assert stale([old]) == [old]

    def test_отсрочка_щедрая(self):
        # Ошибка в сторону молчания дешевле ложной тревоги четыре раза в час.
        assert GRACE_SEC >= 60


class TestЕдинственныйСигнал:
    """Ядро честности модуля: убить зомби нельзя, и модуль не притворяется."""

    def test_зомби_не_получает_ни_одного_сигнала(self):
        sent: list[tuple[int, int]] = []
        z = Zombie(pid=42, ppid=7, comm="celery", age_sec=999.0)
        nudge([z], apply=True, kill=lambda p, s: sent.append((p, s)))
        assert 42 not in [p for p, _ in sent], "по зомби послан сигнал — это ничего не делает"

    def test_родителю_уходит_только_SIGCHLD(self):
        import signal as sig

        sent: list[tuple[int, int]] = []
        z = Zombie(pid=42, ppid=7, comm="celery", age_sec=999.0)
        nudge([z], apply=True, kill=lambda p, s: sent.append((p, s)))
        assert sent == [(7, sig.SIGCHLD)]

    def test_убивающие_сигналы_не_используются_никогда(self):
        import signal as sig

        sent: list[tuple[int, int]] = []
        zs = [Zombie(pid=i, ppid=7, comm="celery", age_sec=999.0) for i in (1, 2, 3)]
        nudge(zs, apply=True, kill=lambda p, s: sent.append((p, s)))
        assert not {s for _, s in sent} & {sig.SIGKILL, sig.SIGTERM, sig.SIGINT}

    def test_один_родитель_получает_один_сигнал(self):
        # Три зомби от одного родителя — один повод, а не три.
        sent: list[tuple[int, int]] = []
        zs = [Zombie(pid=i, ppid=7, comm="celery", age_sec=999.0) for i in (1, 2, 3)]
        nudge(zs, apply=True, kill=lambda p, s: sent.append((p, s)))
        assert len(sent) == 1

    def test_без_apply_не_шлётся_ничего(self):
        sent: list[tuple[int, int]] = []
        z = Zombie(pid=42, ppid=7, comm="celery", age_sec=999.0)
        touched = nudge([z], apply=False, kill=lambda p, s: sent.append((p, s)))
        assert sent == []
        assert touched == [7], "сухой прогон обязан показать, кого бы тронул"

    def test_нулевой_родитель_не_трогается(self):
        # `os.kill(0, …)` бьёт по всей группе процессов, а не по процессу 0.
        # Зомби с нулевым родителем существовать не должен, но цена промаха —
        # сигнал всем соседям.
        sent: list[tuple[int, int]] = []
        z = Zombie(pid=42, ppid=0, comm="celery", age_sec=999.0)
        assert nudge([z], apply=True, kill=lambda p, s: sent.append((p, s))) == []
        assert sent == []

    def test_исчезнувший_родитель_не_роняет_обход(self):
        def boom(pid, s):
            raise ProcessLookupError(pid)

        z = Zombie(pid=42, ppid=7, comm="celery", age_sec=999.0)
        assert nudge([z], apply=True, kill=boom) == []


class TestКонтракт:
    def test_задача_в_расписании(self):
        src = Path(__file__).resolve().parents[1] / "agent_core" / "celery_app.py"
        text = src.read_text("utf-8")
        assert "agora.reap_zombies" in text, "задача не зарегистрирована"
        assert "reap-zombies" in text, "задачи нет в beat_schedule"

    def test_модуль_не_импортирует_celery(self):
        # Тот же довод, что у сборщика осиротевших: разбор /proc — арифметика,
        # и тянуть ради неё брокерную библиотеку значит сделать проверяемое
        # непроверяемым там, где celery не установлен.
        src = (
            Path(__file__).resolve().parents[1]
            / "agent_core" / "maintenance" / "zombies.py"
        )
        text = src.read_text("utf-8")
        code = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        assert "import celery" not in code
        assert "from celery" not in code
