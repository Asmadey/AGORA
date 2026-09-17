"""
Сборка образа воркера падает на том шаге, где сломалось, а не тремя шагами позже.

─── Дефект, который эта проверка закрывает ──────────────────────────────────
В `infra/worker.Dockerfile` установка зависимостей была записана как

    RUN pip install -e ".[dev]" || pip install --upgrade pip

Правая часть `||` выполняется, когда левая упала, и завершается успехом всегда:
pip уже стоит. Значит слой закрывается кодом 0 при НЕ установленных
зависимостях — и BuildKit кэширует его как удачный.

Так и случилось 17.09.2026. Сеть сервера оборвала загрузку на `pydantic>=2.9`
(«from versions: none» при живом индексе), слой завершился успехом, а сборка
упала тремя шагами ниже — на утверждении про opencv, с текстом про потолок
`scenedetect<0.7`. Диагноз в сообщении не имел отношения к причине, а повторный
запуск `deploy.sh` брал сломанный слой из кэша и падал там же за 90 секунд.
Пересборка перестала чинить сборку — это худшее свойство, какое у неё бывает.

Отсюда правило: установка зависимостей не имеет запасного пути. Упало — падает
слой, а не следующий за ним.

─── Второе утверждение: torch не зависит от pyproject ───────────────────────
`COPY services/agent-core/pyproject.toml` стоял ВЫШЕ установки torch. torch
ставится по имени, из своего индекса, и списка зависимостей не читает — но
копирование файла инвалидирует все слои ниже, и правка одной строки в
`pyproject.toml` заставляла качать torch заново.

Цена измерена там же: полоса сервера до PyPI — от 47 до 350 кБ/с, и полная
переустановка занимает часы вместо минут. Перенос `COPY` под установку torch
оставляет тяжёлый слой в кэше при любой правке зависимостей.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOCKERFILE = ROOT / "infra" / "worker.Dockerfile"
TEXT = DOCKERFILE.read_text("utf-8")


def _run_commands() -> list[str]:
    """Тела инструкций RUN с раскрытыми переносами строк."""
    joined = re.sub(r"\\\n\s*", " ", TEXT)
    return [
        line[len("RUN ") :].strip()
        for line in joined.splitlines()
        if line.startswith("RUN ")
    ]


def test_установка_зависимостей_не_имеет_запасного_пути():
    for command in _run_commands():
        if "pip install" not in command:
            continue
        assert "||" not in command, (
            "в образе воркера установка пакетов записана через `||`: "
            f"{command!r}. Запасная ветка завершается успехом при НЕ "
            "установленных зависимостях, BuildKit кэширует слой как удачный, "
            "и сборка падает ниже по течению с посторонним диагнозом"
        )


def test_torch_ставится_до_копирования_pyproject():
    lines = TEXT.splitlines()

    def index_of(pattern: str) -> int:
        for number, line in enumerate(lines):
            if re.search(pattern, line):
                return number
        raise AssertionError(f"в worker.Dockerfile нет строки по шаблону {pattern!r}")

    torch = index_of(r"download\.pytorch\.org/whl/cpu")
    pyproject = index_of(r"^COPY\s+services/agent-core/pyproject\.toml")

    assert torch < pyproject, (
        "COPY pyproject.toml стоит выше установки torch: правка любой "
        "зависимости инвалидирует тяжёлый слой, который от неё не зависит, "
        "и torch качается заново"
    )
