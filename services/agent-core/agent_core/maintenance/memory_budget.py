"""
Бюджет памяти воркера: сколько процессов celery помещается в машину.

─── Что чинится ─────────────────────────────────────────────────────────────
10.09.2026 на боевом нашлось `WORKER_CONCURRENCY=4` при умолчании `1` в
compose. Умолчание там не случайное: рядом лежит замер 04.08.2026 — 5,4 ГБ
anon-rss на один процесс с GigaAM и pyannote — и вывод, что четыре копии в
11,6 ГБ не помещаются никуда.

Не рвануло только потому, что прогоны запускались по одному. Два одновременных
положили бы воркер посреди работы, и проявилось бы это как случайный сбой, а не
как нехватка памяти: `WorkerLostError: signal 9` без указания причины.

Удерживал умолчание КОММЕНТАРИЙ. §5 CLAUDE.md прямо требует оформлять
исключение падающей проверкой, а не комментарием, — комментарий и не удержал.

─── Почему разбирается запущенная команда, а не конфиг ──────────────────────
Файл compose выглядел исправным: `--concurrency=${WORKER_CONCURRENCY:-1}`.
Число приезжало из `.env.local`, который не попадает ни в один дифф и ни в одно
ревью. Проверка, читающая объявленное умолчание, была бы зелёной при живом
дефекте — то есть хуже, чем её отсутствие.

Поэтому источник истины здесь — строка команды работающего процесса.

─── Откуда числа ────────────────────────────────────────────────────────────
Оба замерены, ни одно не назначено. Если машина изменится, менять надо их, а не
формулу.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Сколько держит ОДИН процесс celery с загруженными моделями.
#:
#: Замерено 04.08.2026: anon-rss процесса с large-v3 int8 и pyannote. Движок
#: распознавания с тех пор сменился на GigaAM, порядок величины тот же —
#: 10.09.2026 простаивающий процесс держал 4,18 ГБ остатков от прогона.
PER_PROCESS_GB = 5.4

#: Что занимает всё остальное на той же машине.
#:
#: Замерено 10.09.2026 на боевом при простаивающем воркере: 3,6 ГБ занято, из
#: них воркер — 0,17. Сюда входят web, agent-api, postgres, весь стек LangFuse
#: (он один берёт около 2,4 ГБ) и сама система.
RESERVED_GB = 3.4


@dataclass(frozen=True)
class Verdict:
    fits: bool
    need_gb: float
    have_gb: float
    allowed: int
    reason: str


def max_concurrency(total_gb: float) -> int:
    """Сколько процессов помещается. Ноль — машина мала даже для одного."""
    free = total_gb - RESERVED_GB
    if free < PER_PROCESS_GB:
        return 0
    return int(free // PER_PROCESS_GB)


def budget(*, concurrency: int, total_gb: float) -> Verdict:
    need = concurrency * PER_PROCESS_GB + RESERVED_GB
    allowed = max_concurrency(total_gb)
    fits = need <= total_gb

    if fits:
        reason = (
            f"{concurrency} × {PER_PROCESS_GB} ГБ + {RESERVED_GB} ГБ на остальные службы "
            f"= {need:.1f} ГБ при {total_gb:.1f} ГБ на машине"
        )
    else:
        reason = (
            f"{concurrency} процесс(ов) × {PER_PROCESS_GB} ГБ + {RESERVED_GB} ГБ на остальные "
            f"службы = {need:.1f} ГБ, а на машине {total_gb:.1f} ГБ. "
            f"Помещается {allowed}. Проявится как WorkerLostError посреди прогона, "
            f"а не как нехватка памяти."
        )

    return Verdict(fits=fits, need_gb=need, have_gb=total_gb, allowed=allowed, reason=reason)


#: `--concurrency=4`, `--concurrency 4`. Требует границы слева, иначе
#: `--autoscale=4,1` и подобные читались бы как задание числа процессов.
_LONG = re.compile(r"(?:^|\s)--concurrency[=\s]+(\d+)")
_SHORT = re.compile(r"(?:^|\s)-c[=\s]+(\d+)")


def parse_concurrency(command: str) -> int | None:
    """
    Достаёт число процессов из строки запущенной команды.

    `None` — флага нет, и это НЕ единица: без флага celery берёт число ядер.
    На машине по спецификации (8 vCPU) это восемь процессов, то есть худший
    случай из возможных. Считать отсутствие флага безопасным умолчанием
    значило бы объявить самое опасное состояние нормой.
    """
    for pattern in (_LONG, _SHORT):
        m = pattern.search(command or "")
        if m:
            return int(m.group(1))
    return None


def read_total_gb(
    *,
    cgroup_dir: Path | str = Path("/sys/fs/cgroup"),
    meminfo: Path | str = Path("/proc/meminfo"),
) -> float | None:
    """
    Сколько памяти доступно процессу: сначала потолок контейнера, потом машина.

    `None` — прочитать не удалось. Именно `None`, а не ноль: ноль объявил бы
    негодной любую машину, и проверка начала бы врать в безопасную на вид
    сторону. Неизвестность обязана оставаться неизвестностью.
    """
    limit = Path(cgroup_dir) / "memory.max"
    try:
        raw = limit.read_text().strip()
        if raw != "max":
            return int(raw) / 1024**3
    except (OSError, ValueError):
        pass

    try:
        for line in Path(meminfo).read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024 / 1024**3
    except (OSError, ValueError, IndexError):
        pass

    return None
