# apps/web — Next.js (Node 24, PRD §15). Контекст сборки — корень монорепо.
# syntax=docker/dockerfile:1

FROM node:24-alpine AS deps
WORKDIR /repo
COPY package.json package-lock.json* ./
COPY apps/web/package.json apps/web/package.json
# npm ci требует lock-файл; если его нет — падаем на install, но в CI должен быть ci.
RUN npm ci --workspaces --include-workspace-root || npm install

FROM node:24-alpine AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
# Вложенные зависимости воркспейса: npm ci --workspaces кладёт часть пакетов в
# apps/web/node_modules (например mongodb, xstate), а не в корень. Без копирования
# next build их не резолвит («Can't resolve 'mongodb'»). Это общий случай той же
# болезни, что точечный COPY hash-wasm ниже — здесь лечится корнем, а не пакетом.
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace @agora/web

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1

# Непривилегированный пользователь — контейнер не должен ходить под root.
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# Дистилляция портретов (#24): маршрут /api/portraits/distill исполняет
# services/agent-core/.../distill.py через execFile("python3", …). Код писался в
# расчёте на dev-запуск из каталога репозитория, и образ этому никогда не
# соответствовал: python3 в node:alpine нет, модуля и корпуса тоже. На стенде это
# давало 500 при каждом обращении, а заметно не было, потому что тест #24
# пропускал все три поведенческих кейса безусловной строкой «требует LLM-вызова».
#
# Пакеты pip не нужны: в режиме --no-llm distill.py и загрузчик корпуса
# обходятся стандартной библиотекой, а openai импортируется лениво внутри ветки
# с моделью. Поэтому здесь только интерпретатор и данные.
RUN apk add --no-cache python3

COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/static ./apps/web/.next/static

# hash-wasm (argon2id) — Next.js standalone не включает WASM-модули автоматически.
COPY --from=builder --chown=nextjs:nodejs /repo/node_modules/hash-wasm ./node_modules/hash-wasm

# distill.py вычисляет корень репозитория как parents[4] от своего файла, поэтому
# каталоги обязаны лежать по тем же путям, что и в репозитории: иначе корпус не
# найдётся, а ошибка будет выглядеть как «дистилляция не удалась».
COPY --from=builder --chown=nextjs:nodejs /repo/services/agent-core/agent_core ./services/agent-core/agent_core
COPY --from=builder --chown=nextjs:nodejs /repo/data/grounding ./data/grounding
COPY --from=builder --chown=nextjs:nodejs /repo/prompts ./prompts

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "apps/web/server.js"]