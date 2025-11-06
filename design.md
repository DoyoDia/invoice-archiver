# 🧾 发票归档与管理系统设计文档

## 1. 系统目标

构建一个基于本地 OCR 模型（DeepSeek-OCR）的发票自动归档系统。
功能包括：

* 自动识别与解析中国电子普通发票 PDF；
* 提取核心字段并验证一致性；
* 记录异常与重复；
* 提供前端界面进行查询、导出；
* 支持 Docker Compose 一键部署。

---

## 2. 系统架构概览

### 🧱 组件组成

| 服务             | 技术栈 / 部署方式                     | 主要职责                                      |
| -------------- | ----------------------------------- | ------------------------------------------- |
| **backend**    | FastAPI + Uvicorn（本仓库）              | 文件上传、任务调度、PDF/Markdown 解析、校验、入库 |
| **postgres**   | PostgreSQL 16（Docker Compose）        | 业务数据持久化                                  |
| **llm** _(可选)_ | Ollama + Qwen3-30B（外部或本地服务）       | Markdown→JSON 信息抽取，作为第一解析优先级             |
| **ocr** _(可选)_ | DeepSeek-OCR（HTTP 服务）             | 当 PDF 文本和 LLM 失败时的兜底识别                      |
| **frontend** _(预留)_ | Vue 3 + AntdVue（待实现）            | 概览、查询、导出界面                                  |

---

## 3. 数据流说明

### 🔄 处理流程

1. **上传发票**

   * 用户上传 PDF（批量或单份）。
   * FastAPI 校验大小 ≤100MB、页数 ≤100。
   * 创建 `file_asset` 记录并触发后台任务（async background task）。

2. **解析优先级链路**

   * **优先 LLM**：使用 `pymupdf4llm` 将 PDF 转 Markdown，调用 Ollama（Qwen3-30B）输出结构化 JSON。
   * **次选 PDF 正则解析**：若 LLM 结果缺关键字段，直接解析 `pypdf` 提取的文本（针对竖排/混乱版式做清洗）。
   * **兜底 OCR**：仍失败时调用 DeepSeek-OCR，使用 OCR 文本解析函数生成 JSON。

3. **校验与入库**

   * 校验关键字段与金额一致性；
   * 将合格数据写入数据库；
   * 字段缺失或金额不符 → 写入 `invoice_anomalies`；
   * 检查重复发票并标记 `duplicate` / `conflict_duplicate`。

4. **查询与导出**

   * 前端 / API 查询发票列表、详情；
   * 支持 CSV 导出（UTF-8 with BOM）。

---

## 4. 关键字段与精度要求

### ⚠️ 严格校验字段

| 字段路径        | 说明   | 校验规则                             |
| ----------- | ---- | -------------------------------- |
| `项目[].项目名称` | 项目名  | 必填，非空字符串                         |
| `项目[].规格型号` | 产品型号 | 必填，非空字符串                         |
| `价税合计.小写`   | 总金额  | 必填，数值；必须等于 “合计金额 + 合计税额”，误差≤0.01 |

> 若任一字段缺失或不匹配 → 直接标记为 `error`，并禁止标为 `ok`。

---

## 5. 数据库设计（PostgreSQL）

### 5.1. 表结构概览

#### `file_assets`

| 字段           | 类型                                       | 说明           |
| ------------ | ---------------------------------------- | ------------ |
| id           | serial                                   | 主键           |
| filename     | text                                     | 原文件名         |
| content_hash | varchar(64)                              | SHA-256 文件指纹 |
| size         | bigint                                   | 文件大小（B）      |
| pages        | int                                      | 页数           |
| stored_path  | text                                     | 相对路径         |
| status       | enum(queued,processing,processed,failed) | 状态           |
| error        | text                                     | 错误信息         |
| uploaded_at  | timestamptz                              | 上传时间         |

#### `invoices`

| 字段             | 类型                                               | 说明                |
| -------------- | ------------------------------------------------ | ----------------- |
| id             | serial                                           | 主键                |
| invoice_no     | varchar(32)                                      | 发票号码（唯一）          |
| invoice_type   | text                                             | 发票类型              |
| invoice_date   | date                                             | 开票日期              |
| buyer_name     | text                                             | 购买方               |
| buyer_tax_id   | text                                             | 纳税人识别号            |
| seller_name    | text                                             | 销售方               |
| seller_tax_id  | text                                             | 纳税人识别号            |
| total_amount   | numeric(18,2)                                    | 合计金额              |
| total_tax      | numeric(18,2)                                    | 合计税额              |
| grand_total    | numeric(18,2)                                    | 价税合计（小写）          |
| status         | enum(ok,warn,error,duplicate,conflict_duplicate) | 校验结果              |
| source_file_id | int                                              | 外键 file_assets.id |
| created_at     | timestamptz                                      | 创建时间              |

#### `line_items`

| 字段         | 类型            | 说明   |
| ---------- | ------------- | ---- |
| id         | serial        | 主键   |
| invoice_id | int           | 发票外键 |
| item_name  | text          | 项目名称 |
| spec_model | text          | 规格型号 |
| quantity   | numeric(18,4) | 数量   |
| unit_price | numeric(18,6) | 单价   |
| amount     | numeric(18,2) | 金额   |
| tax_rate   | numeric(5,2)  | 税率   |
| tax_amount | numeric(18,2) | 税额   |

#### `invoice_anomalies`

| 字段         | 类型                    | 说明   |
| ---------- | --------------------- | ---- |
| id         | serial                | 主键   |
| invoice_id | int                   | 外键   |
| severity   | enum(info,warn,error) | 严重程度 |
| code       | text                  | 异常代码 |
| message    | text                  | 错误描述 |
| field_path | text                  | 出错字段 |
| created_at | timestamptz           | 时间戳  |

---

## 6. 异常代码表

| Code                | 严重级别  | 说明                  |
| ------------------- | ----- | ------------------- |
| NULL_FIELD          | error | 关键字段为空              |
| SUM_MISMATCH        | error | 金额不一致（容差0.01）       |
| TAX_RATE_ODD        | warn  | 税率不在 {0,1,3,6,9,13} |
| FORMAT_FAIL         | error | 发票号码格式错误            |
| DATE_PARSE_FAIL     | error | 日期解析失败              |
| OCR_MALFORMED       | error | OCR 返回结构异常          |
| DUPLICATE           | info  | 重复发票（同号同金额）         |
| CONFLICTING_DUP     | error | 同号但金额或日期冲突          |
| SIZE_LIMIT_EXCEEDED | error | 超过 100MB            |
| PAGE_LIMIT_EXCEEDED | error | 超过 100 页            |

---

## 7. 任务流与调度

### 任务调度方式

* FastAPI 使用 `BackgroundTasks` 触发异步处理，无独立 worker 队列。
* `_process_job` 内部使用 `asyncio.Semaphore(1)` 串行化 OCR 调用，防止第三方服务过载。
* LLM 与 PDF 解析可并发运行，多任务取决于 API 实例的工作线程数。
* 失败记录会写回 `job` 和 `file_asset`，便于重试或人工处理。

---

## 8. 接口规范（简表）

| 方法                           | 路径             | 功能 |
| ---------------------------- | -------------- | -- |
| `POST /ingest/files`         | 上传 PDF 发票      |    |
| `GET /jobs/{id}`             | 查询任务状态         |    |
| `GET /invoices`              | 分页筛选（日期、金额、状态） |    |
| `GET /invoices/{invoice_no}` | 查看发票详情         |    |
| `GET /export/invoices.csv`   | 导出汇总           |    |
| `GET /export/line_items.csv` | 导出明细           |    |
| `GET /files/{file_id}`       | 下载原始文件         |    |
| `GET /health`                | 系统状态检查         |    |

---

## 9. 前端模块

### 页面结构

1. **概览页**

   * 总票数 / 异常票 / 待处理 / 重复票
   * 处理趋势图
2. **列表页**

   * 筛选条件：日期、金额区间、状态、项目名称、发票号
   * 状态彩色标识：ok（绿）warn（黄）error（红）duplicate（灰）
3. **详情页**

   * 标准化字段 + 异常提示 + 原始 JSON
4. **上传页**

   * 拖拽上传 PDF，显示队列长度、排队进度
5. **导出页**

   * 导出当前筛选结果为 CSV（UTF-8 with BOM）

---

## 10. Docker 化方案

### 📦 目录结构（当前仓库）

```
invoice-archiver/
├─ backend/
│   ├─ Dockerfile          # 后端镜像构建
│   ├─ main.py
│   ├─ app/
│   └─ requirements.txt
├─ data/                   # 映射到容器内 /data，保存发票及导出文件
├─ docker-compose.yml      # 后端服务编排（加入 1panel-network）
└─ frontend/               # 预留前端目录
```

### ⚙️ Compose 服务

| 服务       | 说明                                                                 |
| ---------- | -------------------------------------------------------------------- |
| backend    | 基于项目 Dockerfile 构建，映射 9000 端口，挂载 `./data` 到容器 `/data`，加入现有 `1panel-network` 网络。 |

> 依赖服务（非 Compose 管理）：
> * **PostgreSQL**：已由 1Panel 部署，容器名 `1Panel-postgresql-MYOJ`。
> * **Ollama**：部署在宿主机（host network），监听 11434。

默认环境变量：

```yaml
DATABASE_URL: postgresql+asyncpg://<user>:<password>@1Panel-postgresql-MYOJ:5432/<database>
STORAGE_ROOT: /data
LLM_BASE_URL: http://host.docker.internal:11434
LLM_MODEL: Qwen3-30B-A3B-Instruct-2507
```

> ⚠️ 请替换 `<user>/<password>/<database>` 为 1Panel PostgreSQL 实际凭据。
> `docker-compose.yml` 已通过 `extra_hosts` 映射 `host.docker.internal -> host-gateway`，确保容器能访问宿主机上的 Ollama 服务。

### ▶️ 启动步骤

1. 确认 Docker 网络 `1panel-network` 已存在（1Panel 默认创建）。
2. 根据实际凭据修改 `docker-compose.yml` 中的 `DATABASE_URL` 和其他环境变量。
3. 运行 `docker compose up --build -d` 启动后台服务并自动加入 `1panel-network`。
4. 首次部署后进入容器执行 `alembic upgrade head` 创建数据库表结构。
5. 通过 `http://localhost:9000/api/health` 验证服务运行情况。

---

## 11. 校验逻辑（重点）

### 校验顺序

1. 关键字段非空；
2. 金额一致性；
3. 税率合法性；
4. 发票号/日期格式；
5. 文件去重。

### 校验伪代码逻辑

```text
if any(项目名称, 规格型号, 价税合计.小写 is null):
    -> error NULL_FIELD

if abs(合计金额 + 合计税额 - 价税合计.小写) > 0.01:
    -> error SUM_MISMATCH

if 税率 not in [0,1,3,6,9,13]:
    -> warn TAX_RATE_ODD
```

---

## 12. 安全与日志

* 所有上传限制 MIME：`application/pdf`
* JWT 用户认证（uploader / viewer / admin）
* 审计：上传、导出、删除操作日志入库
* 日志级别：`INFO` / `ERROR` / `JOB`（任务流水）

