# 发票归档系统 API

- 基础路径：`/api`
- 无鉴权（设计为内网/单机使用）
- 响应格式：`application/json`（导出与下载接口除外）
- 解析为同步：上传后直接返回解析结果

## 接口一览
| 方法 | 路径 | 描述 |
| ---- | ---- | ---- |
| POST | /api/invoices | 上传 PDF，同步解析入库 |
| GET | /api/invoices | 分页检索发票 |
| GET | /api/invoices/summary | 各状态计数 |
| GET | /api/invoices/{invoice_no} | 发票详情 |
| GET | /api/export.csv | 导出当前筛选结果 |
| GET | /api/files/{file_id} | 下载原始 PDF |
| GET | /api/health | 健康检查 |

## 1. 上传发票
**POST /api/invoices** — `multipart/form-data`，字段 `file`（可重复）。单文件 ≤50MB、页数 ≤50。

```json
{
  "results": [
    {"file_id": 1, "invoice_no": "25312000000190830857", "status": "ok", "error": null}
  ]
}
```
`status` 取值：`ok` / `warn` / `error` / `duplicate` / `failed`。

## 2. 发票列表
**GET /api/invoices** — 查询参数（均可选）：`page`(默认1)、`page_size`(≤100)、`invoice_no`、`status`、`date_start`、`date_end`。

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
      "source_file_id": 1,
      "uploaded_at": "2026-05-29T12:05:13"
    }
  ],
  "page": 1, "page_size": 20, "total": 1
}
```

## 3. 状态计数
**GET /api/invoices/summary** → `{"ok": 12, "duplicate": 2, "total": 14}`（仅含出现过的状态，外加 `total`）。

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

## 5. 导出 CSV
**GET /api/export.csv** — 同列表的筛选参数。返回 `text/csv; charset=utf-8`（含 UTF-8 BOM）。

## 6. 下载原文件
**GET /api/files/{file_id}** — 返回 `application/pdf` 附件；不存在返回 404。

## 7. 健康检查
**GET /api/health** → `{"status": "ok", "version": "2.0.0", "llm_fallback": false, "timestamp": "..."}`
