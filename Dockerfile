# AGORA — корневой Dockerfile
# Next.js standalone build for local Docker (self-hosted Postgres, no SSL needed)

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

# hash-wasm (argon2id) — Next.js standalone не включает WASM-модули автоматически.
COPY --from=builder --chown=nextjs:nodejs /repo/node_modules/hash-wasm ./node_modules/hash-wasm

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "apps/web/server.js"]