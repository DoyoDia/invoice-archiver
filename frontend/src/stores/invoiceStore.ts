import { defineStore } from "pinia";
import { reactive, ref } from "vue";
import type { PaginatedResponse } from "../types/api";
import type { InvoiceFilter, InvoiceSummaryRecord } from "../types/invoice";
import { fetchInvoices } from "../services/invoiceService";

const defaultFilter: Required<Pick<InvoiceFilter, "page" | "page_size">> & InvoiceFilter = {
  page: 1,
  page_size: 20
};

export const useInvoiceStore = defineStore("invoices", () => {
  const filter = reactive<InvoiceFilter>({ ...defaultFilter });
  const pageData = ref<PaginatedResponse<InvoiceSummaryRecord>>({ items: [], page: 1, page_size: 20, total: 0 });
  const loading = ref(false);
  const error = ref<string | null>(null);

  const loadInvoices = async (override?: Partial<InvoiceFilter>) => {
    loading.value = true;
    error.value = null;
    try {
      const params = { ...filter, ...override };
      const data = await fetchInvoices(params);
      Object.assign(filter, params);
      pageData.value = data;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      loading.value = false;
    }
  };

  const setFilter = (next: Partial<InvoiceFilter>) => {
    Object.assign(filter, next);
  };

  const resetFilter = () => {
    Object.assign(filter, defaultFilter);
  };

  return {
    filter,
    pageData,
    loading,
    error,
    loadInvoices,
    setFilter,
    resetFilter
  };
});
