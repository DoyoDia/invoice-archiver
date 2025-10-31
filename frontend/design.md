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

| 服务           | 技术栈                               | 主要职责                  |
| ------------ | --------------------------------- | --------------------- |
| **api**      | FastAPI + Uvicorn                 | 文件上传、任务创建、查询、导出       |
| **worker**   | FastAPI Worker + Redis Queue (RQ) | 异步任务执行（PDF→OCR→解析→入库） |
| **postgres** | PostgreSQL 16                     | 业务数据持久化               |
| **redis**    | Redis 7                           | 任务队列与全局锁（OCR 串行）      |
| **ocr**      | DeepSeek-OCR                      | 发票识别（外部 HTTP 服务）      |
| **frontend** | Vue 3 + AntdVue                   | 概览、查询、导出界面            |

---

## 3. 数据流说明

### 🔄 处理流程

1. **上传发票**

   * 用户上传 PDF（批量或单份）。
   * FastAPI 校验大小 ≤100MB、页数 ≤100。
   * 创建 `file_asset` 记录并推入 `ingest` 队列。

2. **渲染与 OCR**

   * worker 从 `ingest` 队列取任务 → 生成页图。
   * 进入 `ocr` 队列（**全局单并发**，Redis 控制）。
   * 调用 DeepSeek-OCR，获得结构化 JSON。

3. **校验与入库**

   * JSON 校验关键字段与金额一致性；
   * 校验结果存入数据库；
   * 若字段缺失或金额不符 → 写入 `invoice_anomalies`；
   * 若重复发票 → 标记 `duplicate` 或 `conflict_duplicate`。

4. **查询与导出**

   * 前端通过 API 查询发票；
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

## 7. 队列与任务流

### 队列结构

| 队列名      | 并发数 | 说明                 |
| -------- | --- | ------------------ |
| ingest   | 2–4 | 文件解析、页数统计、哈希计算     |
| ocr      | 1   | OCR 识别（**全局串行**）   |
| postproc | 2–4 | JSON 校验、数据库写入、异常归档 |

### 全局 OCR 串行控制

* 通过 Redis 队列物理保证并发=1；
* 若未来扩展，可加 Redis 分布式锁保护；
* 超时 120 秒，失败自动重试 2 次；
* 连续失败 3 次 → “死信队列”并标记 `failed`。

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

## 10. Docker Compose 设计

### 📦 目录结构

```
invoice_system/
│
├─ backend/
│   ├─ main.py
│   ├─ worker.py
│   ├─ models/
│   ├─ routes/
│   └─ utils/
│
├─ frontend/
│   └─ （Vue 项目源码）
│
├─ data/
│   ├─ invoices/     # 原始 PDF/图片
│   └─ pg/           # PGSQL 数据卷
│
├─ docker-compose.yml
├─ .env
└─ README.md
```

### ⚙️ 关键环境变量

```env
POSTGRES_USER=invoice
POSTGRES_PASSWORD=invoice123
POSTGRES_DB=invoice_db
DATABASE_URL=postgresql://invoice:invoice123@postgres:5432/invoice_db
REDIS_URL=redis://redis:6379/0
OCR_BASE_URL=http://ocr:8000
MAX_FILE_MB=100
MAX_PAGES=100
AMOUNT_TOLERANCE=0.01
ALLOWED_TAX_RATES=0,1,3,6,9,13
OCR_REQUEST_TIMEOUT=120
OCR_RETRY_MAX=2
TZ=Asia/Shanghai
```

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

