"""FastAPI приложение agent-core — HTTP API для генерации персон и пайплайна.

Запускается через uvicorn::

    uvicorn agent_core.api.app:app --host 0.0.0.0 --port 8001

Маршруты:
    POST /api/personas/generate — генерация синтетических персон (задача #5)
    POST /api/chat/reply        — чат по результатам исследования (задача #28)
    POST /api/export/excel      — выгрузка ответов прогона книгой Excel
    GET  /api/health            — проверка живости

Изоляция по tenant_id — через заголовок X-Tenant-Id (проксируется из сессии
Next.js). Внутри пайплайна (#13+) тенант-контекст устанавливается через
``tenant_scope`` из ``agent_core.db``.
"""

from __future__ import annotations

from fastapi import FastAPI

from agent_core.api.routers import chat, export, matching, personas

app = FastAPI(
    title="AGORA Agent-Core",
    description=(
        "Бэкенд синтетических фокус-групп: генерация персон, "
        "медиа-анализ, симуляция опросов."
    ),
    version="0.1.0",
)

app.include_router(personas.router)
app.include_router(matching.router)
# Чат по результатам исследования (#28). Наружу служба не публикуется: её
# зовёт только веб, уже проверивший сессию и принадлежность прогона.
app.include_router(chat.router)
# Выгрузка ответов в Excel. Здесь, а не в вебе, потому что книгу собирает
# `openpyxl`: §6 запрещает нативные npm-модули в `apps/web`.
app.include_router(export.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}