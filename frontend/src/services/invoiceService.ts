import type { PaginatedResponse } from "../types/api";
import type {
  IngestResult,
  InvoiceCounts,
  InvoiceDetail,
  InvoiceFilter,
  InvoiceSummaryRecord,
  Tag
} from "../types/invoice";
import http from "./http";

export type ExportParams = Omit<InvoiceFilter, "page" | "page_size">;

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

export const fetchSummary = async (): Promise<InvoiceCounts> => {
  const { data } = await http.get<Record<string, number>>("/invoices/summary");
  return {
    total: data.total ?? 0,
    ok: data.ok ?? 0,
    warn: data.warn ?? 0,
    error: data.error ?? 0,
    duplicate: data.duplicate ?? 0
  };
};

export const uploadInvoices = async (files: File[], tags: string[] = []): Promise<IngestResult[]> => {
  const formData = new FormData();
  files.forEach((file) => formData.append("file", file, file.name));
  tags.forEach((t) => formData.append("tags", t));
  const { data } = await http.post<{ results: IngestResult[] }>("/invoices", formData);
  return data.results;
};

export const fetchTags = async (q?: string): Promise<Tag[]> => {
  const { data } = await http.get<Tag[]>("/tags", { params: q ? { q } : {} });
  return data;
};

export const createTag = async (name: string): Promise<Tag> => {
  const { data } = await http.post<Tag>("/tags", { name });
  return data;
};

export const deleteTag = (id: number) => http.delete(`/tags/${id}`);

export const setInvoiceTags = (invoiceNo: string, tags: string[]) =>
  http.put(`/invoices/${invoiceNo}/tags`, { tags });

export const setInvoiceDeleted = (invoiceNo: string, deleted: boolean) =>
  http.post(`/invoices/${invoiceNo}/deleted`, { deleted });

export const exportInvoices = (params: ExportParams, quoteNo = false) => {
  return http.get<Blob>("/export.csv", {
    params: quoteNo ? { ...params, quote_no: true } : params,
    responseType: "blob",
  });
};

export const downloadSourceFile = (fileId: number) => {
  return http.get<Blob>(`/files/${fileId}`, { responseType: "blob" });
};
