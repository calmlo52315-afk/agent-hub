FROM python:3.14-slim AS builder

# 构建依赖
RUN pip install --no-cache-dir uv

WORKDIR /app

COPY runtime/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.14-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

# 从 builder 复制已安装的包
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY runtime /app/runtime
COPY rules /app/rules
COPY runtime/specs /app/runtime/specs

# 创建非 root 用户
RUN addgroup --system --gid 1001 runtime && \
    adduser --system --uid 1001 runtime && \
    chown -R runtime:runtime /app

USER runtime

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8001/healthz')" || exit 1

CMD ["python", "-m", "runtime.server"]
