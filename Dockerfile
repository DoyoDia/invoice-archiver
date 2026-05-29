# 不使用 # syntax 指令，避免从 Docker Hub 拉取 dockerfile 前端镜像（大陆易超时）。

# REGISTRY：base 镜像前缀，默认走 docker.io。大陆可传镜像源前缀，例如：
#   docker build --build-arg REGISTRY=docker.m.daocloud.io/library/ -t invoice-archiver .
ARG REGISTRY=

# --- 前端构建 ---
FROM ${REGISTRY}node:20-slim AS frontend
# 默认用 npmmirror 国内源，可用 --build-arg NPM_REGISTRY=... 覆盖
ARG NPM_REGISTRY=https://registry.npmmirror.com
WORKDIR /frontend
COPY frontend/package.json ./
RUN npm config set registry "$NPM_REGISTRY" && npm install
COPY frontend/ ./
RUN npm run build

# --- 后端运行 ---
FROM ${REGISTRY}python:3.11-slim
# 默认用清华 PyPI 源，可用 --build-arg PIP_INDEX_URL=... 覆盖
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    FRONTEND_DIST=/app/frontend/dist

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
