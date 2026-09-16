"""
Проводка инструментов: собранное должно быть подключено.

─── Зачем отдельный тест ────────────────────────────────────────────────────
`tools.py` и `loop.py` проверены сами по себе двадцатью восемью тестами. Это
ничего не говорит о том, зовёт ли их кто-нибудь. Механизм, построенный и не
подключённый, — тот самый дефект шва, на котором этот проект спотыкался уже
трижды: раздел «Портреты» был отключён от конвейера целиком, и `grep portrait`
по `pipeline/` давал ноль попаданий при живом описании в реестре промптов.

Здесь проверяется шов, а не поведение: кто кого импортирует и зовёт.

─── Почему переключение по размеру, а не флагом ─────────────────────────────
Флаг нужно помнить. Размер контекста измеряется и так, и решение по нему
принимается само: помещается целиком — едем целиком (меньше заходов, модель
видит всё сразу), не помещается — оглавление и инструменты.

Главное — решение не невидимо: оно доезжает до ответа полем `context_mode`.
Молча переключившийся режим объяснял бы разное качество ответов ничем.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = (ROOT / "agent_core" / "api" / "routers" / "chat.py").read_text("utf-8")
CLIENT = (ROOT / "agent_core" / "chat" / "client.py").read_text("utf-8")


def test_маршрут_импортирует_цикл_и_инструменты():
    assert "from ...chat.loop import" in ROUTER or "from ...chat.loop import" in ROUTER
    assert "run_with_tools" in ROUTER, "цикл обязан быть подключён, а не просто написан"


def test_маршрут_зовёт_цикл():
    assert "run_with_tools(" in ROUTER


def test_шлюз_умеет_вызывать_инструменты():
    """
    `stream_reply` отдаёт только текст. Для раундов нужен второй вход, который
    возвращает ещё и вызовы инструментов.
    """
    assert "def call_with_tools" in CLIENT
    assert "tool_calls" in CLIENT, "разбор ответа со вызовами инструментов"


def test_решение_о_режиме_измеряется_а_не_угадывается():
    from agent_core.chat.context import estimate_tokens, needs_tools

    small = {"a": "x" * 100}
    assert not needs_tools(small)
    assert estimate_tokens(small) > 0

    big = {"scenes": [{"text": "щ" * 500} for _ in range(2000)]}
    assert needs_tools(big), "контекст в сотни тысяч токенов обязан уйти на инструменты"


def test_порог_ниже_потолка_модели_с_запасом():
    """
    Порог обязан оставлять место вопросу, истории и ответу. Равный потолку
    порог означал бы отказ ровно на границе — то есть проверку, которая
    срабатывает после того, как всё сломалось.
    """
    from agent_core.chat.context import CONTEXT_LIMIT, TOOLS_THRESHOLD

    assert TOOLS_THRESHOLD < CONTEXT_LIMIT * 0.8, (
        f"порог {TOOLS_THRESHOLD} слишком близок к потолку {CONTEXT_LIMIT}"
    )


def test_режим_доезжает_до_ответа():
    """Переключение, о котором не сказано, объясняет разное качество ничем."""
    assert "context_mode" in ROUTER


def test_оглавление_попадает_в_срез_при_режиме_инструментов():
    from agent_core.chat.context import analyst_context

    pack = {
        "scenes": [
            {"time": "0:00–0:06", "timestamp_sec": 0.0, "end_sec": 6.0,
             "scene_description": "щ" * 400}
            for _ in range(900)
        ],
        "transcript": [],
    }
    ctx = analyst_context(report={}, pack=pack, survey=[], answers=[],
                          qa_flags=[], history=[], with_tools=True)

    vu = ctx["video_understanding"]
    assert "scene_index" in vu, "при инструментах в контексте живёт оглавление"
    assert "scenes" not in vu, "полных описаний в контексте при инструментах нет"
    assert len(vu["scene_index"]) == 900
    assert vu["scene_index"][0]["n"] == 1
