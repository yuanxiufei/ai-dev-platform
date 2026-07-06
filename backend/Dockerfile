FROM python:3.12

ENV PYTHONUNBUFFERED=1

# ── 下载加速 ──
# 清华源（PyPI包国内最快）: https://pypi.tuna.tsinghua.edu.cn/simple
# 阿里云: https://mirrors.aliyun.com/pypi/simple/
# 腾讯云: https://mirrors.cloud.tencent.com/pypi/simple/
ARG UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_INDEX_URL=${UV_INDEX_URL}
ENV UV_HTTP_TIMEOUT=600
ENV UV_CONCURRENT_DOWNLOADS=16
ENV UV_COMPILE_BYTECODE=0
ENV UV_LINK_MODE=copy

RUN pip install uv -i ${UV_INDEX_URL}

WORKDIR /app/
ENV PATH="/app/.venv/bin:$PATH"

# Install dependencies (layer 1: deps only, Docker 层缓存)
COPY ./pyproject.toml /app/
COPY ./ai_models /app/ai_models
COPY ./backend/pyproject.toml ./backend/alembic.ini /app/backend/
COPY ./uv.lock /app/uv.lock
RUN uv sync --frozen --no-install-workspace --group rag

# Copy source code (layer 2: frequent changes)
COPY ./backend/scripts /app/backend/scripts
COPY ./backend/app /app/backend/app

# Sync the project（依赖已在 layer1 装完，这里只安装 app 包）
RUN uv sync --frozen --package app

WORKDIR /app/backend/

# Create a non-root user for security
RUN addgroup --system app && adduser --system --group app

# Ensure the app user owns the application directory
RUN chown -R app:app /app

# Switch to non-root user
USER app

CMD ["fastapi", "run", "--workers", "4", "app/main.py"]
