# 发票归档系统

从 PDF 电子发票中提取字段、归档、检索、下载的轻量系统。面向内网/单机使用。

- **后端**：FastAPI（同步）+ SQLAlchemy + SQLite
- **解析**：PyMuPDF 坐标感知解析，纯 CPU、无外部依赖；可选 LLM 兜底
- **前端**：Vue 3 + Ant Design Vue（上传 / 列表 / 详情）
- **部署**：单容器，`docker compose up` 一键启动

支持单页、多页（明细溢出）、合并发票（一个 PDF 多张）等版式；并提供标签与软删除管理。

详细设计见 [design.md](./design.md)，接口见 [api.md](./api.md)。

### 标签与删除

- **标签**：全局可复用。上传时可统一对一批发票打标签（搜索选择已有或回车快速创建）；
  已入库发票在详情页也能改标签；列表与导出 CSV 都能按标签筛选。
  「管理标签」可全局删除标签（**二次确认**，会从所有发票上移除）。
- **标记删除**（软删除，可切换）：被标记删除的发票在列表中**灰字显示、状态显示「删除」**，
  **不计入统计、不会被导出**；可随时取消删除；**重新上传同号发票会自动恢复**。

### 上传去重

上传页提供两个开关（默认关）：
- **不提交重复的发票**：全库判重，发票号已在库（未删除）则跳过、不入库。
- **不提交重复的发票至标签**：仅在本次所选标签范围内判重，同号发票若已带该标签才跳过（允许同一发票归入不同标签）。

启用后被跳过的发票会在解析结果里标为「已跳过(重复)」，并弹提示告知去掉了几张。

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

## 二·五、中国大陆构建加速

如果构建时报 `failed to resolve ... docker/dockerfile` 或拉取 `node`/`python`
基础镜像超时，是访问 Docker Hub 不稳定所致。本项目已做了两层处理：

1. **pip / npm 已内置国内源**（清华 PyPI + npmmirror），依赖安装不走外网。
2. **`Dockerfile` 去掉了 `# syntax` 指令**，不再拉取 dockerfile 前端镜像。

剩下的就是 `node`/`python` 基础镜像。两种办法二选一：

**办法 A（推荐）：给 Docker 守护进程配置镜像加速器**，一次配置、所有拉取都受益。
编辑 `/etc/docker/daemon.json`：

```json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
```

然后 `sudo systemctl restart docker`，再正常 `docker compose up --build -d`。

**办法 B：构建时临时指定镜像源前缀**（不改全局配置）：

```bash
# compose
REGISTRY=docker.m.daocloud.io/library/ docker compose up --build -d

# 或手动 build
docker build --build-arg REGISTRY=docker.m.daocloud.io/library/ -t invoice-archiver .
```

> 镜像加速器地址会变动，daocloud / 阿里云 / 中科大等都可用，挑一个能连通的即可。
> 也可用 `--build-arg PIP_INDEX_URL=...` / `--build-arg NPM_REGISTRY=...` 换其他源。

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
| `LLM_API_KEY` | （空） | **留空则不启用 LLM**；填入即开启 OpenAI 兼容兜底 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容接口的 base（会自动拼接 `/chat/completions`） |
| `LLM_MODEL` | `deepseek-v4-flash` | LLM 兜底使用的模型名 |
| `LLM_REQUEST_TIMEOUT` | `30` | LLM 请求超时（秒） |

### 关于 SQLite 路径的两种写法
- 三斜杠 `sqlite:///./data/invoices.db` → 相对路径（本地开发用）
- 四斜杠 `sqlite:////data/invoices.db` → 绝对路径 `/data/...`（容器内用，对应挂载卷）

### 可选：开启 LLM 兜底
默认走纯正则坐标解析，已能覆盖标准电子发票。若遇到非标准版式想加一层兜底，
接口走 **OpenAI 兼容格式**（预设 DeepSeek），只需填入 API Key：

```yaml
environment:
  LLM_API_KEY: "sk-xxxxxxxx"              # 填入即启用
  LLM_BASE_URL: "https://api.deepseek.com/v1"
  LLM_MODEL: "deepseek-v4-flash"
```

- 换成其他云服务商：把 `LLM_BASE_URL` 改成对应的 OpenAI 兼容 base、`LLM_MODEL` 改成对应模型即可。
- 本地无鉴权的 OpenAI 兼容服务（如 vLLM、llama.cpp、Ollama 的 `/v1`）：
  `LLM_BASE_URL` 指向本地地址，`LLM_API_KEY` 随便填一个非空值即可开启。
  容器访问宿主机服务需要 `host.docker.internal`，在 compose 里加：
  ```yaml
  extra_hosts:
    - "host.docker.internal:host-gateway"
  ```

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
