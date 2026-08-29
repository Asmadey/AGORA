"""
Чат по результатам исследования (#28) — синхронный агент, не оркестратор.

─── Почему отдельная служба, а не Celery ────────────────────────────────────
Оркестратор живёт внутри задачи Celery, умирает вместе с ней и диалога не
хранит. Очередь при этом занята часовыми прогонами: реплика чата встала бы за
распознаванием речи и ждала бы десятки минут. Чат синхронен по природе.

─── Почему не маршрут Next.js ───────────────────────────────────────────────
В образе веба нет `openai` — см. `lib/server/queue.ts`. Писать агента на
TypeScript значит завести вторую реализацию разбора промптов, `has_support`,
температур и трассировки. Ровно тот класс дефекта, который в этом проекте
повторялся уже трижды.

─── Кто отвечает за доступ ──────────────────────────────────────────────────
Веб. Он проверяет сессию, роль и принадлежность прогона арендатору, и только
потом зовёт эту службу, передавая `tenant_id`. Модель доверия та же, что у
очереди: веб кладёт `tenant_id` в сообщение Celery ровно так же. Служба не
опубликована наружу — она видна только внутри сети compose.

Данные при этом читаются под `tenant_scope`: даже с подделанным `task_id` чужой
прогон не отдастся, потому что политика фильтрует по арендатору.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...chat.agent import META_SEPARATOR, parse_reply
from ...chat.client import stream_reply
from ...chat.context import analyst_context, persona_context

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    tenant_id: str
    task_id: str
    mode: str = Field(pattern="^(analyst|persona)$")
    question: str = Field(min_length=1, max_length=4000)
    persona_id: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    prompts_snapshot: dict[str, Any] = Field(default_factory=dict)


def _prompt_body(key: str, snapshot: dict[str, Any], tenant_id: str) -> str:
    """
    Шаблон промпта: запиннённая версия прогона, иначе файл.

    Тот же порядок, что в конвейере (`nodes._prompt`), и по той же причине:
    правка в Промпт-студии не должна менять задним числом разговор, начатый по
    прежней инструкции.
    """
    from ...paths import find_repo_file
    from ...prompt_text import body_of

    # Значение снимка — объект {id, version, templateSha256}, а не голый
    # идентификатор: так его кладёт buildPromptsSnapshot в вебе. Передать сюда
    # словарь целиком значит получить «cannot adapt type dict» уже в запросе.
    pinned = snapshot.get(key)
    pinned_id = pinned.get("id") if isinstance(pinned, dict) else pinned
    dsn = os.environ.get("DATABASE_URL")

    if pinned_id and dsn:
        import psycopg

        from ...db import tenant_scope

        # Под арендатором, а не голым соединением: на `prompts` включён FORCE
        # RLS, и запрос без роли вернул бы ноль строк — то есть молча увёл бы
        # разговор на файл вместо запиннённой версии.
        with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
            cur.execute("SELECT template FROM prompts WHERE id = %s", (pinned_id,))
            row = cur.fetchone()
            if row and row[0]:
                return body_of(str(row[0]))

    path = find_repo_file(f"prompts/{key}.md")
    if path is None:
        # Промпта нет ни в снимке, ни на диске: отвечать нечем, и придумывать
        # инструкцию на ходу значит отдать пользователю текст, собранный
        # неизвестно по каким правилам.
        raise HTTPException(503, f"промпт {key} не найден ни в снимке прогона, ни в образе")
    return body_of(path.read_text("utf-8"))


def _render(template: str, context: dict[str, Any], question: str) -> str:
    """Подстановка среза в шаблон. Значения — JSON, чтобы структура не терялась."""
    out = template
    for name, value in context.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        out = out.replace("{{" + name + "}}", text)
    return out.replace("{{user_question}}", question)


def _load(tenant_id: str, task_id: str) -> dict[str, Any]:
    """Артефакты завершённого прогона. Чтение только под арендатором."""
    from ...analytics.store import CONTENT_PACKS, REPORT_PERSONAS, REPORTS
    from ...mongo import mongo_db

    db = mongo_db()
    scope = {"tenant_id": tenant_id, "task_id": task_id}
    report = (db[REPORTS].find_one(scope) or {}).get("report") or {}
    pack = (db[CONTENT_PACKS].find_one(scope) or {}).get("pack") or {}
    answers = [doc.get("answer") or doc for doc in db[REPORT_PERSONAS].find(scope)]
    return {"report": report, "pack": pack, "answers": answers}


def _persona(tenant_id: str, persona_id: str) -> dict[str, Any]:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise HTTPException(503, "DATABASE_URL не задан")

    import psycopg

    from ...db import tenant_scope

    with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
        cur.execute("SELECT id, name, dna FROM personas WHERE id = %s::uuid", (persona_id,))
        row = cur.fetchone()
    if not row:
        # Чужая персона и несуществующая неотличимы — так и должно быть.
        raise HTTPException(404, "персона не найдена")
    return {"id": str(row[0]), "name": row[1], "dna": row[2] or {}}


@router.post("/reply")
def reply(request: ChatRequest) -> StreamingResponse:
    """
    Поток ответа. Куски прозы идут как есть, метаблок — последним событием.

    Формат SSE: `data: {"delta": "…"}` на каждый кусок и `data: {"done": …}` в
    конце, где лежат флаги и признак опоры. Разбор метаблока делается ЗДЕСЬ, а
    не в браузере: та же функция, что проверяет опору в отчёте, и вторая её
    реализация на TypeScript разошлась бы с первой.
    """
    data = _load(request.tenant_id, request.task_id)
    if not data["report"]:
        raise HTTPException(404, "отчёт по этому прогону не найден")

    survey = data["report"].get("survey_asked") or []

    if request.mode == "persona":
        if not request.persona_id:
            raise HTTPException(422, "persona_id обязателен в режиме допроса персоны")
        persona = _persona(request.tenant_id, request.persona_id)
        context = persona_context(
            persona=persona, pack=data["pack"], survey=survey,
            answers=data["answers"], history=request.history,
        )
        key = "chat.persona_followup"
    else:
        context = analyst_context(
            report=data["report"], pack=data["pack"], survey=survey,
            answers=data["answers"],
            qa_flags=(data["report"].get("qa_summary") or {}).get("by_kind") or [],
            history=request.history,
        )
        key = "chat.analyst"

    template = _prompt_body(key, request.prompts_snapshot, request.tenant_id)
    user = _render(template, context, request.question)

    def events():
        collected: list[str] = []
        shown = 0  # сколько символов прозы уже отдано
        try:
            for piece in stream_reply(system="", user=user, mode=request.mode):
                collected.append(piece)
                whole = "".join(collected)
                # Метаблок наружу не отдаётся: он служебный. Пока разделителя
                # нет, отдаём всё; как только появился — прозу до него.
                head = whole.split(META_SEPARATOR)[0]
                if len(head) > shown:
                    yield f"data: {json.dumps({'delta': head[shown:]}, ensure_ascii=False)}\n\n"
                    shown = len(head)
        except Exception as exc:  # noqa: BLE001 — отказ обязан дойти до экрана
            failure = json.dumps(
                {"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False
            )
            yield f"data: {failure}\n\n"
            return

        parsed = parse_reply("".join(collected))
        yield "data: " + json.dumps({
            "done": {
                "answer": parsed.answer,
                "grounded": parsed.grounded,
                "insufficient_data": parsed.insufficient_data,
                "out_of_profile": parsed.out_of_profile,
                "contradicts_previous": parsed.contradicts_previous,
                "citations": list(parsed.citations),
            }
        }, ensure_ascii=False) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
