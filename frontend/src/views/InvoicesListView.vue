<template>
  <div class="invoice-list">
    <a-row :gutter="16">
      <a-col v-for="card in summaryCards" :key="card.key" :span="24 / summaryCards.length">
        <a-card size="small">
          <a-statistic :title="card.label" :value="counts[card.key]" :value-style="{ color: card.color }" />
        </a-card>
      </a-col>
    </a-row>

    <a-card class="filter-card mt-16">
      <a-form layout="inline" @submit.prevent>
        <a-form-item label="发票号">
          <a-input v-model:value="filters.invoice_no" placeholder="输入发票号" allow-clear />
        </a-form-item>
        <a-form-item label="状态">
          <a-select v-model:value="filters.status" placeholder="全部" allow-clear style="width: 140px">
            <a-select-option v-for="option in statusOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="日期">
          <a-range-picker v-model:value="dateRange" format="YYYY-MM-DD" />
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button type="primary" @click="onSearch" :loading="invoiceStore.loading">查询</a-button>
            <a-button @click="onReset" :disabled="invoiceStore.loading">重置</a-button>
            <a-button @click="onExport" :loading="exporting">导出 CSV</a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </a-card>

    <a-alert v-if="invoiceStore.error" type="error" :message="invoiceStore.error" show-icon class="mt-16" />

    <a-card class="mt-16">
      <a-table
        :data-source="invoiceStore.pageData.items"
        :columns="columns"
        :pagination="paginationConfig"
        row-key="invoice_id"
        :loading="invoiceStore.loading"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColorMap[record.status]">{{ statusLabelMap[record.status] }}</a-tag>
          </template>
          <template v-else-if="column.key === 'invoice_no'">
            <router-link :to="{ name: 'invoice-detail', params: { invoiceNo: record.invoice_no } }">
              {{ record.invoice_no }}
            </router-link>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type { Dayjs } from "dayjs";
import { message } from "ant-design-vue";
import { useInvoiceStore } from "../stores/invoiceStore";
import { exportInvoices, fetchSummary } from "../services/invoiceService";
import type { InvoiceCounts, InvoiceFilter, InvoiceStatus } from "../types/invoice";

const invoiceStore = useInvoiceStore();

const filters = reactive<InvoiceFilter>({ invoice_no: "", status: undefined });
const dateRange = ref<[Dayjs, Dayjs] | null>(null);
const exporting = ref(false);

const counts = ref<InvoiceCounts>({ total: 0, ok: 0, warn: 0, error: 0, duplicate: 0 });
const summaryCards: Array<{ key: keyof InvoiceCounts; label: string; color: string }> = [
  { key: "total", label: "总计", color: "#1677ff" },
  { key: "ok", label: "正常", color: "#52c41a" },
  { key: "warn", label: "警告", color: "#faad14" },
  { key: "error", label: "异常", color: "#ff4d4f" },
  { key: "duplicate", label: "重复", color: "#8c8c8c" }
];

const statusOptions: Array<{ label: string; value: InvoiceStatus }> = [
  { label: "正常", value: "ok" },
  { label: "警告", value: "warn" },
  { label: "异常", value: "error" },
  { label: "重复", value: "duplicate" }
];
const statusLabelMap: Record<string, string> = { ok: "正常", warn: "警告", error: "异常", duplicate: "重复" };
const statusColorMap: Record<string, string> = { ok: "success", warn: "warning", error: "error", duplicate: "default" };

const columns = [
  { title: "发票号", dataIndex: "invoice_no", key: "invoice_no" },
  { title: "开票日期", dataIndex: "invoice_date", key: "invoice_date" },
  { title: "购买方", dataIndex: "buyer_name", key: "buyer_name" },
  { title: "销售方", dataIndex: "seller_name", key: "seller_name" },
  { title: "金额", dataIndex: "total_amount", key: "total_amount" },
  { title: "税额", dataIndex: "total_tax", key: "total_tax" },
  { title: "价税合计", dataIndex: "grand_total", key: "grand_total" },
  { title: "状态", dataIndex: "status", key: "status" }
];

const paginationConfig = computed(() => ({
  current: invoiceStore.pageData.page,
  pageSize: invoiceStore.pageData.page_size,
  total: invoiceStore.pageData.total,
  showSizeChanger: true,
  pageSizeOptions: ["10", "20", "50", "100"],
  showTotal: (total: number) => `共 ${total} 条`
}));

const buildFilters = (): InvoiceFilter => {
  const payload: InvoiceFilter = { ...filters };
  if (dateRange.value) {
    payload.date_start = dateRange.value[0].format("YYYY-MM-DD");
    payload.date_end = dateRange.value[1].format("YYYY-MM-DD");
  }
  return payload;
};

const refreshSummary = async () => {
  try {
    counts.value = await fetchSummary();
  } catch {
    /* 概览失败不阻塞列表 */
  }
};

const onSearch = () => {
  invoiceStore.loadInvoices({ ...buildFilters(), page: 1 });
};

const onReset = () => {
  filters.invoice_no = "";
  filters.status = undefined;
  dateRange.value = null;
  invoiceStore.resetFilter();
  invoiceStore.loadInvoices({ invoice_no: "", status: undefined, date_start: undefined, date_end: undefined });
};

const onTableChange = (pagination: { current: number; pageSize: number }) => {
  invoiceStore.loadInvoices({ page: pagination.current, page_size: pagination.pageSize });
};

const onExport = async () => {
  exporting.value = true;
  try {
    const { data } = await exportInvoices(buildFilters());
    const url = window.URL.createObjectURL(new Blob([data], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "invoices.csv";
    link.click();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err));
  } finally {
    exporting.value = false;
  }
};

onMounted(() => {
  invoiceStore.loadInvoices({});
  refreshSummary();
});
</script>

<style scoped>
.invoice-list {
  display: flex;
  flex-direction: column;
}

.filter-card {
  border-radius: 8px;
}

.mt-16 {
  margin-top: 16px;
}
</style>
