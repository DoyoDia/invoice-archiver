<template>
  <div class="invoice-list">
    <a-card class="filter-card">
      <a-form layout="inline" @submit.prevent>
        <a-form-item label="发票号">
          <a-input v-model:value="filters.invoice_no" placeholder="输入发票号" allow-clear />
        </a-form-item>
        <a-form-item label="状态">
          <a-select v-model:value="filters.status" placeholder="全部" allow-clear style="width: 160px">
            <a-select-option v-for="option in statusOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="日期">
          <a-range-picker v-model:value="dateRange" format="YYYY-MM-DD" />
        </a-form-item>
        <a-form-item label="金额区间">
          <a-input-number v-model:value="filters.amount_min" placeholder="最小" :min="0" style="width: 100px" />
          <span class="range-sep">~</span>
          <a-input-number v-model:value="filters.amount_max" placeholder="最大" :min="0" style="width: 100px" />
        </a-form-item>
        <a-form-item label="项目名称">
          <a-input v-model:value="filters.item_name" placeholder="支持模糊搜索" allow-clear />
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button type="primary" @click="onSearch" :loading="invoiceStore.loading">查询</a-button>
            <a-button @click="onReset" :disabled="invoiceStore.loading">重置</a-button>
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
            <a-tag :color="statusColorMap[record.status]" class="status-tag">
              {{ statusLabelMap[record.status] }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'invoice_no'">
            <router-link :to="{ name: 'invoice-detail', params: { invoiceNo: record.invoice_no } }">
              {{ record.invoice_no }}
            </router-link>
          </template>
          <template v-else-if="column.key === 'anomaly_codes'">
            <a-space wrap>
              <a-tag v-for="code in record.anomaly_codes" :key="code">{{ code }}</a-tag>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import type { Dayjs } from "dayjs";
import { useInvoiceStore } from "../stores/invoiceStore";
import type { InvoiceFilter, InvoiceStatus } from "../types/invoice";

const invoiceStore = useInvoiceStore();

const filters = reactive<InvoiceFilter>({
  invoice_no: "",
  status: undefined,
  amount_min: undefined,
  amount_max: undefined,
  item_name: ""
});

const dateRange = ref<[Dayjs, Dayjs] | null>(null);

const statusOptions: Array<{ label: string; value: InvoiceStatus }> = [
  { label: "正常", value: "ok" },
  { label: "警告", value: "warn" },
  { label: "异常", value: "error" },
  { label: "重复", value: "duplicate" },
  { label: "冲突重复", value: "conflict_duplicate" }
];

const statusLabelMap: Record<InvoiceStatus, string> = {
  ok: "正常",
  warn: "警告",
  error: "异常",
  duplicate: "重复",
  conflict_duplicate: "冲突重复"
};

const statusColorMap: Record<InvoiceStatus, string> = {
  ok: "success",
  warn: "warning",
  error: "error",
  duplicate: "default",
  conflict_duplicate: "volcano"
};

const columns = [
  { title: "发票号", dataIndex: "invoice_no", key: "invoice_no" },
  { title: "开票日期", dataIndex: "invoice_date", key: "invoice_date" },
  { title: "购买方", dataIndex: "buyer_name", key: "buyer_name" },
  { title: "销售方", dataIndex: "seller_name", key: "seller_name" },
  { title: "金额", dataIndex: "total_amount", key: "total_amount" },
  { title: "税额", dataIndex: "total_tax", key: "total_tax" },
  { title: "价税合计", dataIndex: "grand_total", key: "grand_total" },
  { title: "状态", dataIndex: "status", key: "status" },
  { title: "异常代码", dataIndex: "anomaly_codes", key: "anomaly_codes" },
  { title: "上传时间", dataIndex: "uploaded_at", key: "uploaded_at" }
];

const paginationConfig = computed(() => ({
  current: invoiceStore.pageData.page,
  pageSize: invoiceStore.pageData.page_size,
  total: invoiceStore.pageData.total,
  showSizeChanger: true,
  pageSizeOptions: ["10", "20", "50", "100"],
  showTotal: (total: number) => `共 ${total} 条`
}));

const onSearch = () => {
  const payload: InvoiceFilter = {
    ...filters,
    page: 1,
    page_size: invoiceStore.pageData.page_size
  };

  if (dateRange.value) {
    payload.date_start = dateRange.value[0].format("YYYY-MM-DD");
    payload.date_end = dateRange.value[1].format("YYYY-MM-DD");
  } else {
    payload.date_start = undefined;
    payload.date_end = undefined;
  }

  invoiceStore.loadInvoices(payload);
};

const onReset = () => {
  Object.assign(filters, {
    invoice_no: "",
    status: undefined,
    amount_min: undefined,
    amount_max: undefined,
    item_name: ""
  });
  dateRange.value = null;
  invoiceStore.resetFilter();
  invoiceStore.loadInvoices({});
};

const onTableChange = (pagination: { current: number; pageSize: number }) => {
  invoiceStore.loadInvoices({ page: pagination.current, page_size: pagination.pageSize });
};

watch(
  () => invoiceStore.filter,
  (newFilter: InvoiceFilter) => {
    if (!newFilter.date_start || !newFilter.date_end) {
      dateRange.value = null;
    }
  },
  { deep: true }
);

onMounted(() => {
  invoiceStore.loadInvoices({});
});
</script>

<style scoped>
.invoice-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-card {
  border-radius: 8px;
}

.range-sep {
  margin: 0 8px;
}

.mt-16 {
  margin-top: 16px;
}

.status-tag {
  text-transform: uppercase;
}
</style>
