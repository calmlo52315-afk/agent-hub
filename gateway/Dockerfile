FROM golang:1.25 AS builder

WORKDIR /src

COPY gateway/go.mod gateway/go.sum ./
RUN go mod download

COPY gateway /src

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /out/gateway-server ./cmd/server

FROM debian:bookworm-slim AS runner

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /out/gateway-server /app/gateway-server

# gateway/data 在 .gitignore 中且运行时自动创建，不需要 COPY
# 如果 data 目录存在则创建空目录
RUN mkdir -p /app/data

# 创建非 root 用户
RUN addgroup --system --gid 1001 gateway && \
    adduser --system --uid 1001 gateway && \
    chown -R gateway:gateway /app

USER gateway

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

CMD ["./gateway-server"]
