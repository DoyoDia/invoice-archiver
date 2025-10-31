# 发票归档系统 API 设计文档

## 概览
- 版本：v1（基础路径 `/api`）
- 鉴权：JWT，`Authorization: Bearer <token>`；角色：`uploader`、`viewer`、`admin`
- DEMO Token：`uploader-token` / `viewer-token` / `admin-token`
- 响应格式：`application/json`（导出接口除外）
- 错误结构：统一 `error.code` 与异常表一致
- 任务状态枚举：`queued`、`processing`、`finished`、`failed`、`dead_letter`

## 接口一览
| 方法 | 路径 | 权限 | 描述 |
| ---- | ---- | ---- | ---- |
| POST | /api/ingest/files | uploader/admin | 上传 PDF 并创建处理任务 |
| GET | /api/jobs/{job_id} | 上传者本人/admin | 查询异步任务状态 |
| GET | /api/invoices | viewer+ | 分页检索发票 |
## 1. 上传发票
**POST /api/ingest/files**

- 功能：上传单个或多个 PDF，触发入库流程
- 权限：`uploader`、`admin`
- 请求：`multipart/form-data`
  - `file`：必填，可重复；单文件 ≤100MB；页数 ≤100；MIME=pdf
  - `pages`、`hash`：可选，若提供则用于校验
- 响应
  - 202 Accepted
    ```json
    {
      "jobs": [
    ```
  - 失败：400/413/415/429/500（统一错误格式）

## 2. 查询任务状态
**GET /api/jobs/{job_id}**

- 功能：查询后台处理任务状态
- 权限：上传者本人或 `admin`
- 响应 200
  ```json
  {
    "job_id": "7f27f3d8",
    "status": "processing",
    "step": "ocr",
    "progress": 0.6,
    "error": null,
    "file_id": 128,
  }
  ```

## 3. 发票列表
**GET /api/invoices**

- 权限：`viewer` 及以上
- 查询参数（均可选）
  - `page` 默认 1；`page_size` ≤100
  - `invoice_no`、`status`
  - `date_start`、`date_end`
  - `amount_min`、`amount_max`
  - `item_name`（模糊匹配行项目）
  - `uploaded_by`
- 响应 200
  ```json
  {
    "items": [
      {
        "invoice_id": 512,
        "invoice_no": "25312000000190830857",
        "invoice_date": "2025-06-20",
        "buyer_name": "上海杉达学院",
        "seller_name": "某科技有限公司",
        "total_amount": "1000.00",
        "total_tax": "90.00",
        "grand_total": "1090.00",
        "status": "error",
        "anomaly_codes": ["SUM_MISMATCH"],
        "uploaded_at": "2025-10-30T12:05:13+08:00"
      }
    ],
  }
  ```

## 4. 发票详情
**GET /api/invoices/{invoice_no}**

- 功能：查看单票详细信息（含 OCR 原始 JSON、异常列表、行项目）
- 权限：`viewer` 及以上
- 响应 200
  ```json
  {
    "invoice": {
      "invoice_no": "25312000000190830857",
      "invoice_type": "电子普通发票",
      "invoice_date": "2025-06-20",
      "buyer": {"name": "上海杉达学院", "tax_id": "9131..."},
      "seller": {"name": "某科技有限公司", "tax_id": "9132..."},
      "totals": {"amount": "1000.00", "tax": "90.00", "grand": "1090.00"},
      "status": "error",
      "source_file_id": 128,
      "created_at": "2025-10-30T12:05:13+08:00"
    },
    "line_items": [
      {
        "item_name": "咨询服务费",
        "spec_model": "无",
        "quantity": "1.0000",
        "unit_price": "1000.000000",
        "amount": "1000.00",
        "tax_rate": "9.00",
        "tax_amount": "90.00"
      }
    ],
    "anomalies": [
      {
        "severity": "error",
        "code": "SUM_MISMATCH",
        "message": "合计金额与价税合计不一致",
        "field_path": "价税合计.小写"
  ```

## 5. 导出汇总
**GET /api/export/invoices.csv**
- 响应：`text/csv; charset=utf-8`，包含 UTF-8 BOM，可流式输出

## 6. 导出明细
**GET /api/export/line_items.csv**
- 响应：`text/csv; charset=utf-8`

## 7. 下载原文件
**GET /api/files/{file_id}**
- 权限：`viewer` 及以上；仅可访问有权限的文件
- 响应：`application/pdf` 附件，文件名为原上传名
- 失败：403（越权）、404（不存在）

## 8. 健康检查
**GET /api/health**

- 功能：健康检查，免鉴权
- 响应 200
  ```json
  {
    "status": "ok",
    "version": "1.0.0",
    "timestamp": "2025-10-31T09:00:00+08:00",
    "dependencies": {
      "database": "unknown",
      "redis": "unknown",
      "ocr": "ok",
      "storage": "ok"
    }
  }
  ```

## 统一错误响应示例
```json
{
    "code": "SIZE_LIMIT_EXCEEDED",
    "message": "文件大小超过 100MB",
    "details": {"limit_mb": 100},
    "request_id": "req-1c895"
  }
}
```

- 常见 `code`：`AUTH_REQUIRED`(401)、`FORBIDDEN`(403)、`NOT_FOUND`(404)、`VALIDATION_ERROR`(422)、`RATE_LIMITED`(429)、`INTERNAL_ERROR`(500)

## 下一步
1. 收集 OCR 返回 JSON 样例，完成字段映射与校验规则实现
2. 确认角色与速率限制策略，在后端中落地
3. 与前端对齐筛选项及导出字段，完善字段字典
