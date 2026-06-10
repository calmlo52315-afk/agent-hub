FROM node:24-bookworm-slim AS builder

WORKDIR /app

ARG NEXT_PUBLIC_GATEWAY_BASE_URL=http://gateway:8080
ARG NEXT_PUBLIC_GATEWAY_WS_URL=ws://gateway:8080
ARG NEXT_PUBLIC_DEMO_ACCESS_TOKEN=demo-access-token
ARG GATEWAY_PROXY_TARGET=http://gateway:8080

ENV NEXT_PUBLIC_GATEWAY_BASE_URL=${NEXT_PUBLIC_GATEWAY_BASE_URL}
ENV NEXT_PUBLIC_GATEWAY_WS_URL=${NEXT_PUBLIC_GATEWAY_WS_URL}
ENV NEXT_PUBLIC_DEMO_ACCESS_TOKEN=${NEXT_PUBLIC_DEMO_ACCESS_TOKEN}
ENV GATEWAY_PROXY_TARGET=${GATEWAY_PROXY_TARGET}

# ⭐ 在容器内安装依赖（而非 COPY 宿主机 node_modules）
# lightningcss / @next/swc 等原生模块需要 Linux 二进制
# 不能用 --omit=optional，否则跳过平台原生二进制（lightningcss, sharp 等）
COPY fronted/package.json fronted/package-lock.json* ./
RUN npm install

COPY fronted /app

RUN npm run build

FROM node:24-bookworm-slim AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV NEXT_TELEMETRY_DISABLED=1

# 只复制运行时必要的文件
COPY --from=builder /app/node_modules /app/node_modules
COPY --from=builder /app/.next /app/.next
COPY --from=builder /app/public /app/public
COPY --from=builder /app/package.json /app/package.json
COPY --from=builder /app/next.config.ts /app/next.config.ts

# 创建非 root 用户运行
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs && \
    chown -R nextjs:nodejs /app

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://localhost:3000').then(r => r.ok ? process.exit(0) : process.exit(1)).catch(() => process.exit(1))"

CMD ["npm", "run", "start"]
