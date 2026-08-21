"""
Прогон длиннее часа не должен исполняться дважды.

─── Что случилось ────────────────────────────────────────────────────────────
Прогон 0051 (фильм 50 минут, 19.08.2026) шёл 2 часа 52 минуты. В трассировке он
разорван надвое: первая трасса — `probe_and_normalize`, `extract_audio`,
`detect_speech` до 09:36:19; вторая начинается в 10:35:38 сразу с
`transcribe_and_diarize`. Между ними час, в котором не записано ничего. В
10:41:46 ядро убило процесс celery по нехватке памяти (anon-rss 4.3 ГБ).

Это не два прогона и не сбой модели. Это одна задача, выданная брокером дважды.

─── Механизм ─────────────────────────────────────────────────────────────────
`task_acks_late=True` (и это правильно: падение воркера обязано возвращать
прогон в очередь, а не терять его) означает, что сообщение остаётся
неподтверждённым всё время исполнения. У Valkey/Redis нет подтверждений на
уровне протокола, поэтому kombu эмулирует их таймаутом невидимости:
`visibility_timeout`, по умолчанию **3600 секунд**. Через час после выдачи
сообщение считается потерянным и выдаётся снова — хотя первый экземпляр жив и
работает.

Дальше два экземпляра пайплайна делят одну машину: parakeet и pyannote в двух
копиях не помещаются в память, и один из них умирает. Проявляется это как
случайный OOM в середине прогона, а не как ошибка конфигурации очереди.

─── Почему тест статический ──────────────────────────────────────────────────
`celery` живёт в образе воркера и на хост не ставится (CLAUDE.md §9). Разбор
исходника отвечает на тот же вопрос — задан ли потолок невидимости и больше ли
он жёсткого лимита задачи — и отвечает на любой машине.

Поведенческий уровень добавляется, когда celery доступен: он сверяет
получившуюся конфигурацию с настоящим умолчанием kombu, а не с числом,
переписанным в тест.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "agent_core" / "celery_app.py"

#: Умолчание kombu для Redis-совместимых брокеров. Держим числом здесь только
#: ради читаемости отказа; поведенческий уровень ниже сверяет его с настоящим.
KOMBU_DEFAULT_VISIBILITY_SEC = 3600


def _module() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _module_constants(tree: ast.Module) -> dict[str, ast.AST]:
    """Присваивания верхнего уровня: имя → выражение."""
    out: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
    return out


def _conf_updates(tree: ast.Module) -> dict[str, ast.AST]:
    """
    Аргументы единственного `app.conf.update(...)` в модуле.

    Разбором, а не импортом: импорт потянул бы celery, которого на хосте нет.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "update":
            continue
        return {kw.arg: kw.value for kw in node.keywords if kw.arg}
    raise AssertionError("в celery_app.py нет вызова app.conf.update(...)")


def _value_of(node: ast.AST, consts: dict[str, ast.AST]) -> object:
    """
    Значение выражения настройки — с раскрытием имён модуля и `os.environ.get`.

    Умолчание из `os.environ.get(имя, умолчание)` — это то, что действует на
    сервере, где переменная не задана. Именно его и надо проверять.
    """
    if isinstance(node, ast.Name) and node.id in consts:
        return _value_of(consts[node.id], consts)
    if isinstance(node, ast.Call):
        func = node.func
        # int(...) — прозрачная обёртка
        if isinstance(func, ast.Name) and func.id == "int" and node.args:
            return int(_value_of(node.args[0], consts))
        # os.environ.get(имя, умолчание)
        if isinstance(func, ast.Attribute) and func.attr == "get" and len(node.args) == 2:
            return _value_of(node.args[1], consts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
        left = _value_of(node.left, consts)
        right = _value_of(node.right, consts)
        return left * right if isinstance(node.op, ast.Mult) else left + right
    if isinstance(node, ast.Dict):
        return {
            _value_of(k, consts): _value_of(v, consts)
            for k, v in zip(node.keys, node.values, strict=True)
        }
    return ast.literal_eval(node)


def _setting(name: str) -> object:
    tree = _module()
    conf = _conf_updates(tree)
    assert name in conf, f"настройка {name} не задана в celery_app.py"
    return _value_of(conf[name], _module_constants(tree))


def _has_setting(name: str) -> bool:
    return name in _conf_updates(_module())


def test_visibility_timeout_is_configured():
    """Без явного потолка невидимости работает умолчание в один час."""
    assert _has_setting("broker_transport_options"), (
        "broker_transport_options не задан: брокер возьмёт умолчание kombu "
        f"({KOMBU_DEFAULT_VISIBILITY_SEC} с) и выдаст задачу второй раз через час"
    )
    assert "visibility_timeout" in _setting("broker_transport_options")


def test_visibility_timeout_outlives_the_longest_run():
    """
    Потолок невидимости обязан пережить самый долгий разрешённый прогон.

    Иначе задача, дошедшая до жёсткого лимита, к этому моменту уже исполняется
    во втором экземпляре.
    """
    visibility = _setting("broker_transport_options")["visibility_timeout"]
    hard_limit = _setting("task_time_limit")

    assert visibility > hard_limit, (
        f"невидимость {visibility} с не больше жёсткого лимита задачи {hard_limit} с"
    )


def test_visibility_timeout_beats_the_broker_default():
    """
    Проверка по существу: потолок должен быть больше часа, иначе он ничего не
    меняет — kombu и так ждёт час.
    """
    visibility = _setting("broker_transport_options")["visibility_timeout"]
    assert visibility > KOMBU_DEFAULT_VISIBILITY_SEC


def test_acks_late_is_still_on():
    """
    Соблазн «починить» перевыдачу отключением acks_late закрывается тестом.

    Без него убитый воркер теряет прогон молча: задача подтверждена в момент
    выдачи, и возвращать в очередь нечего.
    """
    assert _setting("task_acks_late") is True


def test_default_of_the_broker_is_what_we_think():
    """Поведенческий уровень: сверка с настоящим умолчанием kombu."""
    kombu_redis = pytest.importorskip(
        "kombu.transport.redis", reason="celery/kombu живут в образе воркера"
    )
    assert kombu_redis.Channel.visibility_timeout == KOMBU_DEFAULT_VISIBILITY_SEC

    from agent_core.celery_app import app

    options = app.conf.broker_transport_options or {}
    assert (
        options.get("visibility_timeout", KOMBU_DEFAULT_VISIBILITY_SEC)
        > app.conf.task_time_limit
    )
