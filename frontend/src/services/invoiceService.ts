import type { PaginatedResponse } from "../types/api";
import type {
  InvoiceCounts,
  InvoiceDetail,
  InvoiceFilter,
  InvoiceSummaryRecord,
  UploadJob
} from "../types/invoice";
import http from "./http";

export interface ExportParams extends Omit<InvoiceFilter, "page" | "page_size"> {}

export const fetchInvoices = async (
  params: InvoiceFilter
): Promise<PaginatedResponse<InvoiceSummaryRecord>> => {
  const { data } = await http.get<PaginatedResponse<InvoiceSummaryRecord>>("/invoices", { params });
  return data;
};

export const fetchInvoiceDetail = async (invoiceNo: string): Promise<InvoiceDetail> => {
  const { data } = await http.get<InvoiceDetail>(`/invoices/${invoiceNo}`);
  return data;
};

export const fetchInvoiceCounts = async (): Promise<InvoiceCounts> => {
  const statusKeys: Array<keyof InvoiceCounts> = [
    "total",
    "ok",
    "warn",
    "error",
    "duplicate",
    "conflict_duplicate"
  ];

  const requests = statusKeys.map((key) => {
    if (key === "total") {
      return http
        .get<PaginatedResponse<InvoiceSummaryRecord>>("/invoices", {
          params: { page: 1, page_size: 1 }
        })
        .then((res: { data: PaginatedResponse<InvoiceSummaryRecord> }) => res.data.total)
        .catch(() => 0);
    }

    return http
      .get<PaginatedResponse<InvoiceSummaryRecord>>("/invoices", {
        params: { page: 1, page_size: 1, status: key }
      })
      .then((res: { data: PaginatedResponse<InvoiceSummaryRecord> }) => res.data.total)
      .catch(() => 0);
  });

  const results = await Promise.all(requests);
  return {
    total: results[0],
    ok: results[1],
    warn: results[2],
    error: results[3],
    duplicate: results[4],
    conflict_duplicate: results[5]
  };
};

export const uploadInvoices = async (files: File[]): Promise<UploadJob[]> => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("file", file);
  });

  const { data } = await http.post<{ jobs: UploadJob[] }>("/ingest/files", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  });

  return data.jobs;
};

export const exportInvoices = (params: ExportParams) => {
  return http.get<Blob>("/export/invoices.csv", {
    params,
    responseType: "blob"
  });
};

export const exportLineItems = (params: ExportParams) => {
  return http.get<Blob>("/export/line_items.csv", {
    params,
    responseType: "blob"
  });
};

export const downloadSourceFile = (fileId: number) => {
  return http.get<Blob>(`/files/${fileId}`, {
    responseType: "blob"
  });
};
