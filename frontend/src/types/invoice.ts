import type { TaskStatus } from "./api";

export type InvoiceStatus =
  | "ok"
  | "warn"
  | "error"
  | "duplicate"
  | "conflict_duplicate";

export interface InvoiceSummaryRecord {
  invoice_id: number;
  invoice_no: string;
  invoice_date: string;
  buyer_name: string;
  seller_name: string;
  total_amount: string;
  total_tax: string;
  grand_total: string;
  status: InvoiceStatus;
  anomaly_codes: string[];
  uploaded_at: string;
}

export interface InvoiceDetail {
  invoice: {
    invoice_no: string;
    invoice_type: string;
    invoice_date: string;
    buyer: { name: string; tax_id: string };
    seller: { name: string; tax_id: string };
    totals: { amount: string; tax: string; grand: string };
    status: InvoiceStatus;
    source_file_id: number;
    created_at: string;
  };
  line_items: Array<{
    item_name: string;
    spec_model: string;
    quantity: string;
    unit_price: string;
    amount: string;
    tax_rate: string;
    tax_amount: string;
  }>;
  anomalies: Array<{
    severity: "info" | "warn" | "error";
    code: string;
    message: string;
    field_path: string;
  }>;
  raw_ocr_json: Record<string, unknown>;
}

export interface InvoiceFilter {
  page?: number;
  page_size?: number;
  invoice_no?: string;
  status?: InvoiceStatus;
  date_start?: string;
  date_end?: string;
  amount_min?: string;
  amount_max?: string;
  item_name?: string;
  uploaded_by?: string;
}

export interface InvoiceCounts {
  total: number;
  ok: number;
  warn: number;
  error: number;
  duplicate: number;
  conflict_duplicate: number;
}

export interface UploadJob {
  job_id: string;
  file_id: number;
  status: TaskStatus;
}
