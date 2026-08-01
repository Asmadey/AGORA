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
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace @agora/web

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1

# Непривилегированный пользователь — контейнер не должен ходить под root.
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/public ./apps/web/public

# TLS-сертификат TimeWeb для sslmode=verify-full (managed Postgres)
RUN apk add --no-cache wget && \
    mkdir -p /certs && \
    wget -q -O /certs/root.crt https://st.timeweb.com/cloud-static/ca.crt && \
    chmod 0600 /certs/root.crt && \
    apk del wget

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
ENV PGSSLROOTCERT=/certs/root.crt
CMD ["node", "apps/web/server.js"]
