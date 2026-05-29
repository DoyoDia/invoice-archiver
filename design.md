# 发票归档系统 设计文档（v2 精简版）

## 目标
从 PDF 电子发票中提取字段、归档、可检索、可下载。面向内网/单机小规模使用，
不追求高并发与多角色权限。

## 技术栈
- 后端：FastAPI（同步路由）+ SQLAlchemy（同步）+ SQLite
- 解析：PyMuPDF 坐标感知解析；可选 LLM 兜底
- 前端：Vue 3 + TypeScript + Ant Design Vue（Upload / List / Detail 三页）
- 部署：单容器，`docker compose up` 一键启动，无外部依赖

## 解析流程
1. **主路径（默认）**：用 PyMuPDF 读取 PDF 文本层的词坐标，按版面还原字段。
   电子发票（全电）模板的标签与数值在纯文本顺序中是错乱的，因此用坐标重建：
   - 发票号码/开票日期/开票人：标签同行右侧取值
   - 购买方/销售方：以 x≈300 为界分左右半区
   - 税号：版面中部、社会信用代码区域，按左右归属
   - 明细行：按列中心 x 坐标把每个单元格归到「单位/数量/单价/金额/税率/税额」
2. **可选 LLM 兜底**：OpenAI 兼容接口（预设 DeepSeek），仅当配置了 `LLM_API_KEY` 时启用。
   主路径解析不充分时，把 PDF 纯文本交给模型抽取 JSON，超时 30s。默认关闭。

解析模块见 `backend/app/parser.py`，对 `test/` 下 14 张真实发票均可正确提取。

## 数据模型（SQLite，3 张表）
- `file_assets`：上传的 PDF（文件名、哈希、大小、页数、存储路径、状态）
- `invoices`：发票主记录（号码、日期、购销方、金额、状态、notes、原始 JSON）
- `line_items`：发票明细行

启动时 `Base.metadata.create_all` 自动建表，无需迁移工具。

## 校验
- `error`：发票号缺失 / 无明细 / 价税合计缺失 / 合计金额+税额 ≠ 价税合计
- `warn`：明细税率不在 {0,1,3,6,9,13}%
- `duplicate`：发票号已存在
校验结果汇总进 `invoices.notes`，状态进 `invoices.status`。

## 存储
PDF 落盘到 `${STORAGE_ROOT}/invoices/{file_id}_{原名}`；SQLite 在 `${STORAGE_ROOT}/invoices.db`。
容器中 `STORAGE_ROOT=/data`，挂载到宿主 `./data`。

## 配置（环境变量）
| 变量 | 默认 | 说明 |
| ---- | ---- | ---- |
| DATABASE_URL | sqlite:///./data/invoices.db | 数据库连接 |
| STORAGE_ROOT | data | PDF 与 DB 存储根目录 |
| MAX_FILE_MB | 50 | 单文件大小上限 |
| MAX_PAGES | 50 | 单文件页数上限 |
| ALLOWED_TAX_RATES | 0,1,3,6,9,13 | 允许的税率（%） |
| LLM_API_KEY | （空） | 填入则启用 LLM 兜底 |
| LLM_BASE_URL | https://api.deepseek.com/v1 | OpenAI 兼容接口 base |
| LLM_MODEL | deepseek-v4-flash | 模型名 |
| LLM_REQUEST_TIMEOUT | 30 | LLM 超时秒数 |

## 运行
```bash
# Docker（推荐，含前端）
docker compose up --build      # 访问 http://localhost:8000

# 本地开发
cd backend && pip install -r requirements.txt
uvicorn backend.main:app --app-dir .. --port 8000
cd frontend && npm install && npm run dev   # 访问 http://localhost:5173
```
