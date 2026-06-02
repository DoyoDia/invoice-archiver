# 发票归档系统 API

- 基础路径：`/api`
- 无鉴权（设计为内网/单机使用）
- 响应格式：`application/json`（导出与下载接口除外）
- 解析为同步：上传后直接返回解析结果

## 接口一览
| 方法 | 路径 | 描述 |
| ---- | ---- | ---- |
| POST | /api/invoices | 上传 PDF，同步解析入库（可同时打标签） |
| GET | /api/invoices | 分页检索发票（含已删除，灰显） |
| GET | /api/invoices/summary | 各状态计数（不含已删除） |
| GET | /api/invoices/{invoice_no} | 发票详情 |
| PUT | /api/invoices/{invoice_no}/tags | 设置某发票的标签 |
| POST | /api/invoices/{invoice_no}/deleted | 标记/取消删除 |
| GET | /api/tags | 列出/搜索标签 |
| POST | /api/tags | 创建标签 |
| PUT | /api/tags/{tag_id} | 重命名标签（全局生效） |
| DELETE | /api/tags/{tag_id} | 删除标签（全局，从所有发票移除） |
| GET | /api/export.csv | 导出当前筛选结果（排除已删除） |
| GET | /api/files/{file_id} | 下载原始 PDF |
| GET | /api/health | 健康检查 |

## 1. 上传发票
**POST /api/invoices** — `multipart/form-data`：
- `file`：必填，可重复；单文件 ≤50MB、页数 ≤50
- `tags`：可选，可重复；本批所有发票统一打上这些标签（不存在的标签自动创建）

```json
{
  "results": [
    {"file_id": 1, "invoice_no": "25312000000190830857", "status": "ok", "error": null, "revived": false}
  ]
}
```
- `status` 取值：`ok` / `warn` / `error` / `duplicate` / `failed`
- `revived`：为 `true` 表示命中了同号的「已删除」记录并将其恢复更新（不新建重复记录）

## 2. 发票列表
**GET /api/invoices** — 查询参数（均可选）：`page`(默认1)、`page_size`(≤100)、`invoice_no`、`status`、`date_start`、`date_end`、`tag`(按标签名筛选)。返回包含已删除发票（`deleted=true`），由前端灰显。

```json
{
  "items": [
    {
      "invoice_id": 1,
      "invoice_no": "25312000000190830857",
      "invoice_date": "2025-06-20",
      "buyer_name": "上海杉达学院",
      "seller_name": "某科技有限公司",
      "total_amount": "1000.00",
      "total_tax": "90.00",
      "grand_total": "1090.00",
      "status": "ok",
      "deleted": false,
      "tags": ["打车", "5月报销"],
      "source_file_id": 1,
      "uploaded_at": "2026-05-29T12:05:13"
    }
  ],
  "page": 1, "page_size": 20, "total": 1
}
```

## 3. 状态计数
**GET /api/invoices/summary** → `{"ok": 12, "duplicate": 2, "total": 14}`（仅含出现过的状态，外加 `total`；已删除发票不计入）。

## 4. 发票详情
**GET /api/invoices/{invoice_no}**

```json
{
  "invoice": {
    "invoice_no": "25312000000190830857",
    "invoice_type": "电子发票（普通发票）",
    "invoice_date": "2025-06-20",
    "buyer": {"name": "上海杉达学院", "tax_id": "5231..."},
    "seller": {"name": "某科技有限公司", "tax_id": "9231..."},
    "totals": {"amount": "1000.00", "tax": "90.00", "grand": "1090.00"},
    "status": "ok",
    "notes": null,
    "deleted": false,
    "tags": ["打车", "5月报销"],
    "source_file_id": 1,
    "created_at": "2026-05-29T12:05:13"
  },
  "line_items": [
    {"item_name": "*广告服务*广告制作费", "spec_model": null, "quantity": "1.0000",
     "unit_price": "1000.000000", "amount": "1000.00", "tax_rate": "9.00", "tax_amount": "90.00"}
  ],
  "raw_json": { "...解析得到的原始字典..." }
}
```
`notes` 汇总校验提示（如「金额不一致」「重复发票号」），无异常时为 `null`。

## 5. 标签与删除

**PUT /api/invoices/{invoice_no}/tags** — body `{"tags": ["打车", "5月报销"]}`，整体替换该发票的标签。→ `{"ok": true, "tags": [...]}`

**POST /api/invoices/{invoice_no}/deleted** — body `{"deleted": true}` 标记删除、`false` 取消。→ `{"ok": true, "deleted": true}`。已删除发票仍在列表显示（灰显、状态「删除」），但不计入统计、不被导出；重新上传同号发票会自动恢复。

**GET /api/tags?q=** — 列出标签（`q` 模糊搜索）→ `[{"id": 1, "name": "打车"}]`

**POST /api/tags** — body `{"name": "打车"}` 创建（已存在则返回原标签）→ `{"id": 1, "name": "打车"}`

**PUT /api/tags/{tag_id}** — body `{"name": "网约车"}` 重命名（全局生效，所有发票上的该标签同步更新）→ `{"id": 1, "name": "网约车"}`；新名为空或与其它标签重名返回 400。

**DELETE /api/tags/{tag_id}** — 全局删除标签，并从所有发票上移除关联 → `{"ok": true}`

## 6. 导出 CSV
**GET /api/export.csv** — 同列表的筛选参数（`invoice_no` / `status` / `date_start` / `date_end` / `tag`），外加：
- `quote_no=true`：发票号前加单引号，避免老版本 Excel 转科学计数法，文件名为 `invoices_quoted.csv`

**已标记删除的发票不会被导出。** 同一发票号只导出最新上传的一条（自动去重，重新导入的修正版本胜出，避免旧异常/重复记录污染导出）。返回 `text/csv; charset=utf-8`（含 UTF-8 BOM）。

## 7. 下载原文件
**GET /api/files/{file_id}** — 返回 `application/pdf` 附件；不存在返回 404。

## 8. 健康检查
**GET /api/health** → `{"status": "ok", "version": "2.0.0", "llm_fallback": false, "timestamp": "..."}`
