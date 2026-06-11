# MemoCortex 后端 Dockerfile — 用于 Render.com / Railway / 任意 PaaS

FROM python:3.11-slim

# 装系统依赖 (sqlite-utils 等)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 装 uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# 复制依赖文件先装 (Docker layer cache)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

# 复制业务代码
COPY app ./app
COPY mcp_server ./mcp_server

# 运行时数据目录
ENV MEMOCORTEX_DATA_DIR=/data
RUN mkdir -p /data && chmod 777 /data

EXPOSE 8765

# 启动 FastAPI (Render 自动设 $PORT)
CMD ["sh", "-c", "uv run uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8765}"]
