"""
Сборщик зомби-процессов внутри контейнера воркера.

─── Что чинится ─────────────────────────────────────────────────────────────
08.09.2026 два дочерних процесса celery умерли и остались в таблице процессов
зомби. Провисели двое суток и ушли только тогда, когда контейнер пересоздали
10.09.2026. Стоило это двух слотов PID и ничего больше — но ровно так же
выглядит начало настоящей утечки: родитель, переставший забирать детей, копит
их до исчерпания таблицы процессов, и первым это заметит не мониторинг, а
`fork: Resource temporarily unavailable` посреди прогона.

─── Чего этот модуль не делает, и почему никто не может ─────────────────────
Не убивает зомби. Зомби — уже мёртвый процесс: от него осталась строка с кодом
возврата, которого не забрал родитель. `SIGKILL` по зомби не операция, а
обращение к покойнику; ядро его молча проглотит.

Исчезает зомби двумя способами: родитель вызывает `wait()`, либо родитель
умирает и зомби переходит к `init`, который забирает всегда.

Поэтому единственный сигнал, который модуль посылает, — `SIGCHLD` родителю.
Он безвреден по определению: действие по умолчанию — игнорировать, убить им
нельзя ничего. Родителю с обработчиком он даёт повод дойти до `waitpid`.

Не убивает родителя. Родитель здесь — главный процесс celery, то есть сам
воркер. Убить его посреди прогона значит поменять два слота PID на потерянный
прогон. Если подталкивание не помогло, модуль докладывает, и перезапуск
назначает человек — как и у сборщика осиротевших прогонов.

─── Почему отсрочка обязательна ─────────────────────────────────────────────
Родитель забирает ребёнка за миллисекунды, и зомби возрастом в секунду — это
нормальное завершение процесса. Проверка без отсрочки кричала бы на каждом
здоровом выходе четыре раза в час, и на её крик перестали бы смотреть.
"""

from __future__ import annotations

import argparse
import os
import signal
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Сколько зомби вправе провисеть, прежде чем это станет поводом.
#:
#: Минута — три порядка запаса к нормальному времени сборки (миллисекунды).
#: Ошибка в сторону молчания стоит задержки на один цикл расписания; ошибка в
#: обратную сторону стоит доверия к проверке.
GRACE_SEC = 60


@dataclass(frozen=True)
class Zombie:
    pid: int
    ppid: int
    comm: str
    age_sec: float


def _parse_stat(
    raw: str, *, uptime_sec: float, clock_ticks: int
) -> tuple[str, int, str, float] | None:
    """
    Разбирает строку `/proc/<pid>/stat`. `None` — процесс не зомби.

    Имя процесса лежит в скобках и может содержать и пробелы, и сами скобки
    (`Web Content`, `sh (old)`). Поэтому граница ищется по ПОСЛЕДНЕЙ `)`, а не
    делением по пробелам: наивный `split()` съезжает на поле, состояние
    читается из имени, и зомби теряется молча.
    """
    try:
        open_at = raw.index("(")
        close_at = raw.rindex(")")
    except ValueError:
        return None

    comm = raw[open_at + 1 : close_at]
    rest = raw[close_at + 1 :].split()
    if len(rest) < 20:
        return None

    state = rest[0]
    if state != "Z":
        return None

    ppid = int(rest[1])
    # Двадцать второе поле stat — starttime в тиках с момента загрузки.
    # После закрывающей скобки идут поля с третьего, поэтому смещение 22-3=19.
    starttime_ticks = int(rest[19])
    age = uptime_sec - starttime_ticks / clock_ticks
    return state, ppid, comm, max(age, 0.0)


def read_zombies(
    proc_root: Path | str = Path("/proc"), *, clock_ticks: int | None = None
) -> list[Zombie]:
    """
    Обходит `/proc` и возвращает зомби с их возрастом.

    Исчезнувший на середине обхода процесс — штатная гонка, а не отказ: между
    перечислением каталогов и чтением `stat` проходит время, и здоровая система
    в этот промежуток завершает процессы постоянно.
    """
    root = Path(proc_root)
    ticks = clock_ticks if clock_ticks is not None else os.sysconf("SC_CLK_TCK")

    try:
        uptime_sec = float((root / "uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return []

    found: list[Zombie] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "stat").read_text()
        except OSError:
            continue

        parsed = _parse_stat(raw, uptime_sec=uptime_sec, clock_ticks=ticks)
        if parsed is None:
            continue

        _, ppid, comm, age = parsed
        found.append(Zombie(pid=int(entry.name), ppid=ppid, comm=comm, age_sec=age))

    return found


def stale(zombies: Iterable[Zombie], grace_sec: float = GRACE_SEC) -> list[Zombie]:
    """Отсеивает свежих: молодой зомби — это штатно завершившийся процесс."""
    return [z for z in zombies if z.age_sec > grace_sec]


def nudge(
    zombies: Sequence[Zombie],
    *,
    apply: bool,
    kill: Callable[[int, int], None] = os.kill,
) -> list[int]:
    """
    Шлёт родителям `SIGCHLD`. Возвращает список тронутых (или тронутых бы) PID.

    Единственный посылаемый сигнал — `SIGCHLD`, и посылается он ТОЛЬКО
    родителю. По самому зомби не шлётся ничего: это не сработало бы, а код,
    который делает бесполезное, читается как работающий.

    Один родитель получает один сигнал, сколько бы детей за ним ни числилось:
    три зомби от одного процесса — один повод, а не три.
    """
    parents = sorted({z.ppid for z in zombies})
    touched: list[int] = []

    for ppid in parents:
        # `os.kill(0, …)` бьёт по всей группе процессов, а не по процессу 0.
        # Зомби с нулевым родителем существовать не должен, но цена промаха
        # здесь — сигнал всем соседям, поэтому проверка стоит строки.
        if ppid <= 0:
            continue
        if not apply:
            touched.append(ppid)
            continue
        try:
            kill(ppid, signal.SIGCHLD)
        except ProcessLookupError:
            # Родитель ушёл сам — значит зомби уже перешли к init и будут
            # забраны. Это успех, а не отказ.
            continue
        except PermissionError:
            continue
        touched.append(ppid)

    return touched


def sweep(*, apply: bool = False, proc_root: Path | str = Path("/proc")) -> dict[str, Any]:
    """Полный проход: найти, отсеять свежих, подтолкнуть родителей."""
    zombies = read_zombies(proc_root)
    old = stale(zombies)
    return {
        "total": len(zombies),
        "stale": [
            {"pid": z.pid, "ppid": z.ppid, "comm": z.comm, "minutes": int(z.age_sec // 60)}
            for z in old
        ],
        "parents_nudged": nudge(old, apply=apply),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборщик зомби-процессов")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="только показать (по умолчанию)")
    mode.add_argument("--apply", action="store_true", help="послать родителям SIGCHLD")
    parser.add_argument("--proc", default="/proc", help="корень procfs (для проверки)")
    args = parser.parse_args()

    result = sweep(apply=args.apply, proc_root=args.proc)

    if not result["stale"]:
        print(f"Зависших зомби нет (всего зомби в таблице: {result['total']}).")
        return 0

    for z in result["stale"]:
        print(f"PID {z['pid']} ({z['comm']}) — зомби {z['minutes']} мин, родитель {z['ppid']}")

    if args.apply:
        print(f"Родителям послан SIGCHLD: {result['parents_nudged'] or 'некому'}")
    else:
        print(f"Послал бы SIGCHLD: {result['parents_nudged'] or 'некому'} (сухой прогон)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
