# AGORA — корневой Dockerfile для TimeWeb App Platform
#
# TimeWeb App Platform требует Dockerfile в корне репозитория.
# Реальный Dockerfile — в infra/web.Dockerfile (сборка Next.js standalone).
# Этот файл делегирует туда.
#
# Вариант деплоя в панели TimeWeb:
#   Тип: Dockerfile
#   Источник: GitHub → Asmadey/AGORA → main
#   Dockerfile: /Dockerfile (этот файл, в корне)

FROM node:24-alpine AS deps
WORKDIR /repo
COPY package.json package-lock.json* ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci --workspaces --include-workspace-root || npm install

FROM node:24-alpine AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace @agora/web

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/static ./apps/web/.next/static

# TLS-сертификат TimeWeb для sslmode=verify-full (managed Postgres)
# chmod 0644 — сертификат должен быть читаем пользователем nextjs (uid 1001)
RUN apk add --no-cache wget && \
    mkdir -p /certs && \
    wget -q -O /certs/root.crt https://st.timeweb.com/cloud-static/ca.crt && \
    chmod 0644 /certs/root.crt && \
    apk del wget

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
ENV PGSSLROOTCERT=/certs/root.crt
CMD ["node", "apps/web/server.js"]