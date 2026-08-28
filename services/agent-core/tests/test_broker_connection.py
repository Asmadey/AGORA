"""
Соединение с Valkey переживает долгий узел.

─── Что случилось ────────────────────────────────────────────────────────────
Прогон 0052 (21.08.2026) упал через **61 минуту** после старта:

    ConnectionError: Error 32 while writing to socket. Broken pipe.

В логе воркера это помечено как `Exception raised outside body` — то есть отказ
пришёл не из пайплайна, а из собственного обращения Celery к брокеру: подтвердить
задачу и записать результат.

Механизм. Пока идёт длинный узел — распознавание пятидесятиминутного фильма
занимает больше часа, — по соединению с Valkey не передаётся НИЧЕГО. Простаивающее
соединение закрывает либо сам Valkey по своему `timeout`, либо промежуточное
сетевое оборудование. Клиент об этом не знает: сокет выглядит открытым, и узнаёт
он о разрыве в момент записи — то есть после того, как работа уже сделана.

Час работы и оплаченные вызовы модели теряются на последнем шаге.

─── Чем лечится ──────────────────────────────────────────────────────────────
Тремя вещами сразу, и все три нужны:

* **keepalive** — операционная система сама шлёт пробники и держит соединение
  живым через промежуточное оборудование;
* **проверка здоровья** — клиент периодически сам пингует и переоткрывает
  соединение, если оно умерло, ДО того как в него что-то писать;
* **повтор при разрыве** — если разрыв всё же случился между проверкой и
  записью, попытка повторяется на новом соединении вместо отказа задачи.

Только keepalive недостаточно: он не спасает от закрытия сервером по `timeout`.
Только проверка здоровья недостаточна: между проверкой и записью есть окно.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "agent_core"


def _module(rel: str) -> ast.Module:
    return ast.parse((PKG / rel).read_text(encoding="utf-8"))


def _conf_update_keywords() -> dict[str, ast.AST]:
    for node in ast.walk(_module("celery_app.py")):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update"
        ):
            return {kw.arg: kw.value for kw in node.keywords if kw.arg}
    raise AssertionError("в celery_app.py нет вызова app.conf.update(...)")


def _transport_options() -> dict:
    conf = _conf_update_keywords()
    assert "broker_transport_options" in conf, "broker_transport_options не задан"
    tree = _module("celery_app.py")
    consts = {
        target.id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    def value(node: ast.AST):
        if isinstance(node, ast.Name) and node.id in consts:
            return value(consts[node.id])
        if isinstance(node, ast.Dict):
            return {value(k): value(v) for k, v in zip(node.keys, node.values, strict=True)}
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
            left, right = value(node.left), value(node.right)
            return left * right if isinstance(node.op, ast.Mult) else left + right
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "int" and node.args:
                return int(value(node.args[0]))
            if isinstance(func, ast.Attribute) and func.attr == "get" and len(node.args) == 2:
                return value(node.args[1])
        return ast.literal_eval(node)

    return value(conf["broker_transport_options"])


def test_broker_keeps_the_socket_alive():
    """Простаивающее соединение обязано подавать признаки жизни."""
    options = _transport_options()
    assert options.get("socket_keepalive") is True, (
        "без keepalive соединение с брокером умирает на длинном узле, и задача "
        "падает при подтверждении — уже после того, как работа сделана"
    )


def test_broker_checks_health_before_writing():
    """
    Проверка здоровья с интервалом заметно меньше часа.

    Час — это то, через сколько упал прогон 0052; проверка, идущая реже отказа,
    не проверяет ничего.
    """
    options = _transport_options()
    interval = options.get("health_check_interval")
    assert isinstance(interval, int) and 0 < interval <= 300, (
        f"health_check_interval={interval!r}: нужен интервал в пределах пяти минут"
    )


def test_our_own_client_is_configured_too():
    """
    Клиент воркера (`pipeline/tasks.py`) настраивается наравне с брокером.

    Celery и наш код ходят в Valkey по РАЗНЫМ соединениям: настроить одно и
    забыть второе значит починить половину — и половина отказов останется, а
    выглядеть будет как «иногда падает».
    """
    source = (PKG / "pipeline" / "tasks.py").read_text(encoding="utf-8")
    assert "socket_keepalive" in source, "у клиента воркера нет keepalive"
    assert "health_check_interval" in source, "у клиента воркера нет проверки здоровья"
    assert "retry_on_error" in source or "retry=" in source, (
        "у клиента воркера нет повтора при разрыве"
    )
