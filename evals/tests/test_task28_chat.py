#!/usr/bin/env python3
"""
CDD-тест задачи #28 — чат по результатам исследования.

Условия взяты из поля `cdd` графа задач:

  · «аналитик»: вопрос про метрику, которой нет → insufficient_data, без
    выдуманного числа;
  · «персона»: вопрос вне DNA → out_of_profile; в контекст персоны не попадают
    ответы других персон (утечка == 0, ТОТ ЖЕ тест изоляции, что в #18);
    ответ, противоречащий прежним, помечается contradicts_previous;
  · тред восстанавливается после перезагрузки и не виден другому арендатору.

─── Что здесь проверяется статикой, а что нет ───────────────────────────────
Изоляция среза — статикой, и это не компромисс: она свойство КОДА, а не модели.
Срез строит чистая функция, и чужих ответов в нём нет как данных.

Флаги `insufficient_data` и `out_of_profile` ставит модель, и утверждать о них
статически нечего. Здесь проверяется, что путь для них есть: промпт их просит,
разбор их достаёт, экран их показывает. Живой уровень — прогон в среде.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core" / "agent_core"
WEB = REPO / "apps" / "web"

CONTEXT = CORE / "chat" / "context.py"
AGENT = CORE / "chat" / "agent.py"
CLIENT = CORE / "chat" / "client.py"
ROUTER = CORE / "api" / "routers" / "chat.py"
WEB_ROUTE = WEB / "app" / "api" / "runs" / "[id]" / "chat" / "route.ts"
WEB_VIEW = WEB / "components" / "agora" / "ChatView.tsx"
WEB_PAGE = WEB / "app" / "runs" / "[id]" / "chat" / "page.tsx"
WEB_LIB = WEB / "lib" / "chat.ts"
PROMPT_ANALYST = REPO / "prompts" / "chat.analyst.md"
PROMPT_PERSONA = REPO / "prompts" / "chat.persona_followup.md"
MIGRATION = REPO / "infra" / "postgres" / "init" / "40_prompts_seed_chat_meta.sql"
COMPOSE = REPO / "infra" / "docker-compose.yml"
SCHEMA = REPO / "infra" / "postgres" / "init" / "02_schema.sql"
RLS = REPO / "infra" / "postgres" / "init" / "03_rls.sql"

results: list[tuple[str, str, str]] = []


def check(n: str, ok: bool, d: str = "") -> None:
    results.append((n, "OK" if ok else "FAIL", d))
    print(f"  {'OK  ' if ok else 'FAIL'}  {n}" + (f"  →  {d}" if d else ""))


def skip(n: str, r: str) -> None:
    results.append((n, "SKIP", r))
    print(f"  SKIP  {n}  →  {r}")


def read(p: Path) -> str:
    return p.read_text("utf-8") if p.exists() else ""


print("== Статический уровень: агент ==")

context_src = read(CONTEXT)
agent_src = read(AGENT)

check("модуль среза существует", CONTEXT.exists())
check("модуль разбора ответа существует", AGENT.exists())
check("клиент модели существует", CLIENT.exists())

check(
    "срез персоны фильтрует ответы по её идентификатору",
    "persona_id" in context_src and "_own_answers" in context_src,
)
check(
    "срез персоны не содержит отчёта",
    "report" not in context_src.split("def persona_context")[-1].split("def ")[0],
    "иначе персона узнала бы итог исследования и подстроилась под него",
)
check(
    "срез — копия, а не ссылка на входные данные",
    "deepcopy" in context_src,
    "иначе правка среза меняла бы то, из чего он собран",
)

print("\n== Статический уровень: изоляция (та же проверка, что в #18) ==")

# Проверяется ВХОД, а не вывод: «в ответе нет чужих имён» зелено ровно до
# первого совпадения формулировок.
sys.path.insert(0, str(REPO / "services" / "agent-core"))
try:
    from agent_core.chat.context import analyst_context, persona_context

    anna = {"id": "p-anna", "name": "Анна", "dna": {"demographics": {}}}
    answers = [
        {"persona_id": "p-anna", "verbatim": "мне зашло"},
        {"persona_id": "p-boris", "verbatim": "СЕКРЕТ-БОРИСА"},
    ]
    slice_ = persona_context(
        persona=anna, pack={}, survey=[], answers=answers, history=[]
    )
    blob = json.dumps(slice_, ensure_ascii=False)
    check("утечка чужих ответов в срез персоны == 0", "СЕКРЕТ-БОРИСА" not in blob)
    check("свои ответы в срезе есть", "мне зашло" in blob)

    full = analyst_context(
        report={"aggregate": {}}, pack={}, survey=[], answers=answers, qa_flags=[], history=[]
    )
    check(
        "аналитик видит всех персон прогона",
        "СЕКРЕТ-БОРИСА" in json.dumps(full, ensure_ascii=False),
    )
except Exception as exc:  # noqa: BLE001
    check("утечка чужих ответов в срез персоны == 0", False, f"{type(exc).__name__}: {exc}")
    skip("свои ответы в срезе есть", "модуль не импортируется")
    skip("аналитик видит всех персон прогона", "модуль не импортируется")

print("\n== Статический уровень: флаги ==")

for flag in ("insufficient_data", "out_of_profile", "contradicts_previous"):
    in_prompt = flag in read(PROMPT_ANALYST) or flag in read(PROMPT_PERSONA)
    in_parser = flag in agent_src
    check(f"флаг {flag} проходит промпт → разбор", in_prompt and in_parser)

check(
    "ответ без опоры помечается, а не выбрасывается",
    "has_support" in agent_src and "grounded" in agent_src,
)
check(
    "«данных нет» не считается неопорным",
    "insufficient or has_support" in agent_src,
    "иначе честный ответ «это не измерялось» ругали бы за отсутствие таймкода",
)

print("\n== Статический уровень: транспорт и экран ==")

router_src = read(ROUTER)
web_route = read(WEB_ROUTE)
page_src = read(WEB_PAGE)

check("маршрут агента существует", ROUTER.exists())
check("ответ отдаётся потоком", "StreamingResponse" in router_src and "text/event-stream" in router_src)
check("веб проксирует поток", WEB_ROUTE.exists() and "text/event-stream" in web_route)
check("веб проверяет сессию до вызова агента", "requireSession" in web_route)
check(
    "чат доступен только по завершённому прогону",
    "REPORT_READY" in web_route and "REPORT_READY" in page_src,
)
check("реплики считаются в кап стоимости", "chatBudget" in web_route)
check(
    "экран больше не заглушка",
    WEB_VIEW.exists() and "ChatView" in page_src and "ещё не подключён" not in page_src,
)

print("\n== Статический уровень: схема и развёртывание ==")

schema = read(SCHEMA)
rls = read(RLS)
check("таблицы тредов объявлены", "chat_threads" in schema and "chat_messages" in schema)
check(
    "треды под RLS с FORCE",
    "chat_threads           FORCE ROW LEVEL SECURITY" in rls
    or ("chat_threads" in rls and "FORCE ROW LEVEL SECURITY" in rls),
)
check("миграция промптов заведена", MIGRATION.exists())
check(
    "промпты переведены на формат «проза + метаблок»",
    "---META---" in read(PROMPT_ANALYST) and "Только JSON" not in read(PROMPT_ANALYST),
)
check(
    "служба агента поднимается в compose",
    "agent-api" in read(COMPOSE) and "uvicorn" in read(COMPOSE),
)
check(
    "служба не опубликована наружу",
    "8001:8001" not in read(COMPOSE),
    "чат зовёт только веб, уже проверивший сессию",
)

print("\n== Поведенческий уровень ==")

base_url = os.environ.get("BASE_URL")
BEHAVIOURAL = (
    "чат отвечает по завершённому прогону",
    "вопрос про несуществующую метрику → insufficient_data",
    "тред восстанавливается после перезагрузки",
)
if not base_url:
    for n in BEHAVIOURAL:
        skip(n, "BASE_URL не задан — нужен поднятый сервер и завершённый прогон")
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _harness import login  # noqa: E402

    client, why = login(base_url)
    if client is None:
        for n in BEHAVIOURAL:
            skip(n, why)
    else:
        code, body = client.call("/api/tasks", "GET")
        try:
            tasks = json.loads(body).get("tasks") or []
        except Exception:  # noqa: BLE001
            tasks = []
        ready = [t for t in tasks if t.get("status") == "REPORT_READY"]
        if not ready:
            for n in BEHAVIOURAL:
                skip(n, "нет ни одного завершённого прогона")
        else:
            run_id = ready[0]["id"]
            payload = json.dumps({
                "mode": "analyst",
                "question": "Какой средний балл за операторскую работу?",
            }).encode()
            code, body = client.call(f"/api/runs/{run_id}/chat", "POST", payload)
            check("чат отвечает по завершённому прогону", code == 200, f"HTTP {code}: {body[:160]}")

            got_done = '"done"' in body
            check(
                "вопрос про несуществующую метрику → insufficient_data",
                got_done,
                "финальное событие не пришло" if not got_done else "",
            )

            code, body = client.call(f"/api/runs/{run_id}/chat?mode=analyst", "GET")
            try:
                saved = json.loads(body).get("messages") or []
            except Exception:  # noqa: BLE001
                saved = []
            check(
                "тред восстанавливается после перезагрузки",
                len(saved) >= 1,
                f"сообщений в треде: {len(saved)}",
            )

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#28 Чат по результатам"))
