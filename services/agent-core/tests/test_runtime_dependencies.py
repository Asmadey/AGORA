"""
То, что импортирует боевой код, объявлено в ОСНОВНЫХ зависимостях.

─── Дыра, которую эта проверка закрывает ────────────────────────────────────
`test_dependencies_declared.py` спрашивает у среды, разрешается ли имя пакета.
В CI окружение собирается командой `pip install -e ".[dev]"`, а образ воркера
на стадии runtime делает `pip install -e .` — без extras.

Значит пакет, объявленный только в `[project.optional-dependencies] dev`,
проходит проверку в CI и отсутствует в бою. Отказ приходит
`ModuleNotFoundError` при первом обращении — то есть после оплаченных
расшифровки, разбора кадров и опроса персон, ровно когда за результатом пришли.

Так уже было с `openpyxl`: он лежал в `dev` с подписью «чтение исходных анкет»,
а выгрузка ответов заказчику — боевой путь.

─── Почему сверка со списком здесь уместна ──────────────────────────────────
В соседнем тесте сверка со списком отвергнута сознательно: часть пакетов
приходит транзитивно и по делу, и такой тест краснел бы на правильном коде.
Здесь сверяются не ВСЕ импорты, а ровно те, что перечислены ниже поимённо, —
то есть список ведётся не «на всякий случай», а под конкретную границу
«extras против основных».
"""
from __future__ import annotations

import pathlib
import re

CORE = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT = (CORE / "pyproject.toml").read_text("utf-8")

#: Пакеты, которые импортирует боевой код воркера.
#:
#: Список короткий намеренно: сюда попадает то, без чего падает оплаченный
#: прогон, а не всё подряд.
RUNTIME_PACKAGES = ("openai", "openpyxl", "pymongo", "psycopg", "boto3")


#: Имя пакета в строке зависимости: за ним идут extras, оператор сравнения или
#: пробел. Скобка обязательна — `psycopg[binary,pool]>=3.2` объявлен именно так,
#: и шаблон без неё молча не находил бы объявленную зависимость.
_DECL = r'"{name}[\[><=~ ]'


def _section(name: str) -> str:
    """Тело секции pyproject от заголовка до следующего заголовка."""
    match = re.search(rf"^\[{re.escape(name)}\](.*?)(?=^\[)", PYPROJECT, re.S | re.M)
    return match.group(1) if match else ""


def test_боевые_пакеты_не_живут_в_extras():
    main = _section("project")
    dev = re.search(r"^dev = \[(.*?)^\]", PYPROJECT, re.S | re.M)
    dev_body = dev.group(1) if dev else ""

    for package in RUNTIME_PACKAGES:
        declared = re.search(_DECL.format(name=re.escape(package)), main)
        assert declared, (
            f"{package} не объявлен в основных зависимостях: образ воркера ставит "
            f"`pip install -e .` без extras, и в бою пакета не будет"
        )
        assert not re.search(_DECL.format(name=re.escape(package)), dev_body), (
            f"{package} продублирован в extras dev — две записи разойдутся молча"
        )


def test_список_боевых_пакетов_не_пуст_и_осмыслен():
    """Пустой список превратил бы проверку в зелёную заглушку."""
    assert len(RUNTIME_PACKAGES) >= 5
    assert "openpyxl" in RUNTIME_PACKAGES, "выгрузка заказчику — боевой путь, а не dev-утилита"
