export type InvoiceStatus = "ok" | "warn" | "error" | "duplicate";

export interface InvoiceSummaryRecord {
  invoice_id: number;
  invoice_no: string;
  invoice_date: string | null;
  buyer_name: string | null;
  seller_name: string | null;
  total_amount: string | null;
  total_tax: string | null;
  grand_total: string | null;
  status: InvoiceStatus;
  deleted: boolean;
  tags: string[];
  source_file_id: number;
  uploaded_at: string;
}

export interface Tag {
  id: number;
  name: string;
}

export interface InvoiceDetail {
  invoice: {
    invoice_no: string;
    invoice_type: string | null;
    invoice_date: string | null;
    buyer: { name: string | null; tax_id: string | null };
    seller: { name: string | null; tax_id: string | null };
    totals: { amount: string | null; tax: string | null; grand: string | null };
    status: InvoiceStatus;
    notes: string | null;
    deleted: boolean;
    tags: string[];
    source_file_id: number;
    created_at: string;
  };
  line_items: Array<{
    item_name: string | null;
    spec_model: string | null;
    quantity: string | null;
    unit_price: string | null;
    amount: string | null;
    tax_rate: string | null;
    tax_amount: string | null;
  }>;
  raw_json: Record<string, unknown>;
}

export interface InvoiceFilter {
  page?: number;
  page_size?: number;
  invoice_no?: string;
  status?: string; // 单个状态，或逗号分隔（如 "ok,duplicate" = 正常&重复）
  date_start?: string;
  date_end?: string;
  tag?: string;
}

export interface InvoiceCounts {
  total: number;
  ok: number;
  warn: number;
  error: number;
  duplicate: number;
}

export interface IngestResult {
  file_id: number;
  invoice_no: string | null;
  status: string;
  error?: string | null;
}
