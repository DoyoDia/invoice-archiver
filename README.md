# 发票归档系统

从 PDF 电子发票中提取字段、归档、检索、下载的轻量系统。面向内网/单机使用。

- **后端**：FastAPI（同步）+ SQLAlchemy + SQLite
- **解析**：PyMuPDF 坐标感知解析，纯 CPU、无外部依赖；可选 LLM 兜底
- **前端**：Vue 3 + Ant Design Vue（上传 / 列表 / 详情）
- **部署**：单容器，`docker compose up` 一键启动

详细设计见 [design.md](./design.md)，接口见 [api.md](./api.md)。

---

## 一、快速开始（Docker Compose，推荐）

只需要装好 Docker 和 Docker Compose，在项目根目录执行：

```bash
docker compose up --build -d
```

构建完成后访问 **http://localhost:8000** 即可（前端和 API 都在这个端口）。

- 首次会同时构建前端（Node）和后端（Python），耗时几分钟
- 数据持久化到宿主机 `./data` 目录（SQLite 数据库 + 上传的 PDF）
- 停止：`docker compose down`（数据保留）；查看日志：`docker compose logs -f`

升级代码后重新构建：

```bash
docker compose up --build -d
```

---

## 二、手动 docker build（不用 compose）

```bash
# 1. 在项目根目录构建镜像（注意 build context 是当前目录 .）
docker build -t invoice-archiver .

# 2. 运行容器，挂载数据卷并映射端口
docker run -d \
  --name invoice-archiver \
  -p 8000:8000 \
  -v "$(pwd)/data:/data" \
  -e DATABASE_URL="sqlite:////data/invoices.db" \
  -e STORAGE_ROOT="/data" \
  invoice-archiver
```

> 提示：`Dockerfile` 是多阶段构建——先用 `node:20-slim` 把前端打包成静态文件，
> 再由 `python:3.11-slim` 里的 FastAPI 一并托管，所以最终只有一个容器。

---

## 三、配置（环境变量）

所有配置都通过环境变量传入，在 `docker-compose.yml` 的 `environment:` 下修改，
或用 `docker run -e KEY=VALUE` 传入。

| 变量 | 默认值 | 说明 |
| ---- | ---- | ---- |
| `DATABASE_URL` | `sqlite:///./data/invoices.db` | 数据库连接串；容器内用绝对路径 `sqlite:////data/invoices.db` |
| `STORAGE_ROOT` | `data` | PDF 与 SQLite 文件的存储根目录；容器内为 `/data` |
| `MAX_FILE_MB` | `50` | 单个 PDF 大小上限（MB） |
| `MAX_PAGES` | `50` | 单个 PDF 页数上限 |
| `ALLOWED_TAX_RATES` | `0,1,3,6,9,13` | 允许的税率（%），超出则标记为 `warn` |
| `AMOUNT_TOLERANCE` | `0.01` | 金额校验容差 |
| `TZ` | `Asia/Shanghai` | 时区 |
| `LLM_BASE_URL` | （空） | **留空则不启用 LLM**；填入本地 Ollama 地址即开启兜底 |
| `LLM_MODEL` | `qwen3:14b` | LLM 兜底使用的模型名 |
| `LLM_REQUEST_TIMEOUT` | `30` | LLM 请求超时（秒） |

### 关于 SQLite 路径的两种写法
- 三斜杠 `sqlite:///./data/invoices.db` → 相对路径（本地开发用）
- 四斜杠 `sqlite:////data/invoices.db` → 绝对路径 `/data/...`（容器内用，对应挂载卷）

### 可选：开启 LLM 兜底
默认走纯正则坐标解析，已能覆盖标准电子发票。若遇到非标准版式想加一层兜底，
在宿主机跑一个 Ollama，然后配置：

```yaml
environment:
  LLM_BASE_URL: "http://host.docker.internal:11434"
  LLM_MODEL: "qwen3:14b"
```

> 容器访问宿主机服务需要 `host.docker.internal`，在 compose 里加：
> ```yaml
> extra_hosts:
>   - "host.docker.internal:host-gateway"
> ```

---

## 四、数据持久化与备份

所有数据都在挂载的 `./data` 目录下：

```
data/
├── invoices.db          # SQLite 数据库（发票记录、明细）
└── invoices/            # 归档的原始 PDF 文件
    └── 1_xxx.pdf
```

备份只需打包整个 `data/` 目录即可。删除 `invoices.db` 会在下次启动时自动重建空表。

---

## 五、本地开发（不用 Docker）

**后端**：

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 从项目根目录的角度启动
uvicorn backend.main:app --app-dir .. --port 8000 --reload
```

**前端**：

```bash
cd frontend
npm install      # 或 pnpm install
npm run dev      # 访问 http://localhost:5173，已配置代理转发 /api 到 8000
```

---

## 六、健康检查

```bash
curl http://localhost:8000/api/health
# {"status":"ok","version":"2.0.0","llm_fallback":false,"timestamp":"..."}
```

`llm_fallback` 字段反映当前是否启用了 LLM 兜底。
