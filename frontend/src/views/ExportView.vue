<template>
  <div class="export-view">
    <a-card title="导出筛选" class="filter-card">
      <a-form layout="vertical" @submit.prevent>
        <a-row :gutter="16">
          <a-col :xs="24" :md="12" :lg="8">
            <a-form-item label="发票号">
              <a-input v-model:value="filters.invoice_no" placeholder="输入发票号" allow-clear />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12" :lg="8">
            <a-form-item label="状态">
              <a-select v-model:value="filters.status" placeholder="全部" allow-clear>
                <a-select-option v-for="option in statusOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12" :lg="8">
            <a-form-item label="项目名称">
              <a-input v-model:value="filters.item_name" placeholder="支持模糊搜索" allow-clear />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12" :lg="8">
            <a-form-item label="日期">
              <a-range-picker v-model:value="dateRange" format="YYYY-MM-DD" />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12" :lg="8">
            <a-form-item label="金额区间">
              <a-input-number v-model:value="filters.amount_min" placeholder="最小" :min="0" style="width: 100%" />
              <span class="range-sep">~</span>
              <a-input-number v-model:value="filters.amount_max" placeholder="最大" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-space>
          <a-button type="primary" @click="onExportInvoices" :loading="exporting">导出汇总</a-button>
          <a-button @click="onExportLineItems" :loading="exporting">导出明细</a-button>
          <a-button @click="onReset" :disabled="exporting">重置</a-button>
        </a-space>
      </a-form>
    </a-card>

    <a-alert v-if="messageText" :type="messageType" :message="messageText" show-icon class="mt-16" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import type { Dayjs } from "dayjs";
import { exportInvoices, exportLineItems } from "../services/invoiceService";
import type { InvoiceFilter, InvoiceStatus } from "../types/invoice";

const filters = reactive<InvoiceFilter>({});
const dateRange = ref<[Dayjs, Dayjs] | null>(null);
const exporting = ref(false);
const messageText = ref("");
const messageType = ref<"success" | "error">("success");

const statusOptions: Array<{ label: string; value: InvoiceStatus }> = [
  { label: "正常", value: "ok" },
  { label: "警告", value: "warn" },
  { label: "异常", value: "error" },
  { label: "重复", value: "duplicate" },
  { label: "冲突重复", value: "conflict_duplicate" }
];

const buildParams = () => {
  const params: Record<string, unknown> = { ...filters };
  if (dateRange.value) {
    params.date_start = dateRange.value[0].format("YYYY-MM-DD");
    params.date_end = dateRange.value[1].format("YYYY-MM-DD");
  }
  delete params.page;
  delete params.page_size;
  return params;
};

const triggerDownload = (blob: Blob, filename: string) => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

const onExportInvoices = async () => {
  exporting.value = true;
  messageText.value = "";
  try {
    const response = await exportInvoices(buildParams());
    triggerDownload(response.data, "invoices.csv");
    messageType.value = "success";
    messageText.value = "汇总导出完成";
  } catch (err) {
    messageType.value = "error";
    messageText.value = err instanceof Error ? err.message : String(err);
  } finally {
    exporting.value = false;
  }
};

const onExportLineItems = async () => {
  exporting.value = true;
  messageText.value = "";
  try {
    const response = await exportLineItems(buildParams());
    triggerDownload(response.data, "line_items.csv");
    messageType.value = "success";
    messageText.value = "明细导出完成";
  } catch (err) {
    messageType.value = "error";
    messageText.value = err instanceof Error ? err.message : String(err);
  } finally {
    exporting.value = false;
  }
};

const onReset = () => {
  Object.keys(filters).forEach((key) => {
    delete (filters as Record<string, unknown>)[key];
  });
  dateRange.value = null;
  messageText.value = "";
};
</script>

<style scoped>
.export-view {
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
</style>
