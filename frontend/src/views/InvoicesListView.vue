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
        <a-form-item label="标签">
          <a-select
            v-model:value="filters.tag"
            show-search
            allow-clear
            placeholder="按标签筛选"
            style="width: 160px"
            :options="tagOptions"
          />
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button type="primary" @click="onSearch" :loading="invoiceStore.loading">查询</a-button>
            <a-button @click="onReset" :disabled="invoiceStore.loading">重置</a-button>
            <a-button @click="onExport" :loading="exporting">导出 CSV</a-button>
            <a-tooltip title="发票号前加单引号，避免老版本 Excel 转成科学计数法">
              <a-button @click="onExportQuoted" :loading="exportingQuoted">导出'csv'</a-button>
            </a-tooltip>
            <a-button @click="manageVisible = true">管理标签</a-button>
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
        :row-class-name="rowClassName"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag v-if="record.deleted" color="default">删除</a-tag>
            <a-tag v-else :color="statusColorMap[record.status]">{{ statusLabelMap[record.status] }}</a-tag>
          </template>
          <template v-else-if="column.key === 'invoice_no'">
            <router-link :to="{ name: 'invoice-detail', params: { invoiceNo: record.invoice_no } }">
              {{ record.invoice_no }}
            </router-link>
          </template>
          <template v-else-if="column.key === 'tags'">
            <a-tag v-for="tag in record.tags" :key="tag" color="blue">{{ tag }}</a-tag>
            <span v-if="!record.tags.length" class="muted">—</span>
          </template>
          <template v-else-if="column.key === 'uploaded_at'">
            {{ formatTime(record.uploaded_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-button type="link" size="small" @click="openTagEdit(record)">编辑标签</a-button>
            <a-button type="link" size="small" @click="onToggleDeleted(record)">
              {{ record.deleted ? "取消删除" : "标记删除" }}
            </a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 编辑某发票的标签：弹窗即二次确认 -->
    <a-modal
      v-model:open="tagEditVisible"
      :title="`编辑标签 · ${tagEditNo}`"
      ok-text="确定"
      cancel-text="取消"
      :confirm-loading="tagEditSaving"
      @ok="saveTagEdit"
    >
      <a-select
        v-model:value="tagEditValues"
        mode="tags"
        style="width: 100%"
        placeholder="选择或输入标签（回车创建），可删除已有标签"
        :options="tagOptions"
      />
    </a-modal>

    <!-- 管理标签：新增 + 删除（删除带二次确认） -->
    <a-modal v-model:open="manageVisible" title="管理标签" :footer="null">
      <a-space style="width: 100%; margin-bottom: 12px">
        <a-input
          v-model:value="newTagName"
          placeholder="输入新标签名"
          style="width: 220px"
          @press-enter="addTag"
        />
        <a-button type="primary" @click="addTag">添加</a-button>
      </a-space>
      <div v-if="allTags.length" class="tag-manage">
        <div v-for="t in allTags" :key="t.id" class="tag-manage-row">
          <a-tag color="blue">{{ t.name }}</a-tag>
          <a-popconfirm
            title="确认删除该标签？将从所有发票上移除"
            ok-text="删除"
            cancel-text="取消"
            @confirm="onDeleteTag(t)"
          >
            <a-button type="text" danger size="small">删除</a-button>
          </a-popconfirm>
        </div>
      </div>
      <a-empty v-else :image="false" description="暂无标签" />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import dayjs, { type Dayjs } from "dayjs";
import { message } from "ant-design-vue";
import { useInvoiceStore } from "../stores/invoiceStore";
import {
  createTag,
  deleteTag,
  exportInvoices,
  fetchSummary,
  fetchTags,
  setInvoiceDeleted,
  setInvoiceTags
} from "../services/invoiceService";
import type {
  InvoiceCounts,
  InvoiceFilter,
  InvoiceStatus,
  InvoiceSummaryRecord,
  Tag
} from "../types/invoice";

const invoiceStore = useInvoiceStore();

const filters = reactive<InvoiceFilter>({ invoice_no: "", status: undefined, tag: undefined });
const dateRange = ref<[Dayjs, Dayjs] | null>(null);
const exporting = ref(false);
const exportingQuoted = ref(false);

const allTags = ref<Tag[]>([]);
const tagOptions = computed(() => allTags.value.map((t) => ({ value: t.name, label: t.name })));

// 管理标签弹窗
const manageVisible = ref(false);
const newTagName = ref("");

// 编辑某发票标签弹窗
const tagEditVisible = ref(false);
const tagEditNo = ref("");
const tagEditValues = ref<string[]>([]);
const tagEditSaving = ref(false);

const loadTags = async () => {
  try {
    allTags.value = await fetchTags();
  } catch {
    /* 标签加载失败不阻塞列表 */
  }
};

const addTag = async () => {
  const name = newTagName.value.trim();
  if (!name) return;
  try {
    await createTag(name);
    newTagName.value = "";
    await loadTags();
    message.success(`已添加标签「${name}」`);
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err));
  }
};

const onDeleteTag = async (tag: Tag) => {
  try {
    await deleteTag(tag.id);
    message.success(`已删除标签「${tag.name}」`);
    if (filters.tag === tag.name) filters.tag = undefined;
    await loadTags();
    invoiceStore.loadInvoices({});
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err));
  }
};

const openTagEdit = (record: InvoiceSummaryRecord) => {
  tagEditNo.value = record.invoice_no;
  tagEditValues.value = [...record.tags];
  tagEditVisible.value = true;
};

const saveTagEdit = async () => {
  tagEditSaving.value = true;
  try {
    await setInvoiceTags(tagEditNo.value, tagEditValues.value);
    tagEditVisible.value = false;
    message.success("标签已更新");
    await loadTags();
    invoiceStore.loadInvoices({});
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err));
  } finally {
    tagEditSaving.value = false;
  }
};

const rowClassName = (record: InvoiceSummaryRecord) => (record.deleted ? "row-deleted" : "");

const onToggleDeleted = async (record: InvoiceSummaryRecord) => {
  try {
    await setInvoiceDeleted(record.invoice_no, !record.deleted);
    invoiceStore.loadInvoices({});
    refreshSummary();
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err));
  }
};

const counts = ref<InvoiceCounts>({ total: 0, ok: 0, warn: 0, error: 0, duplicate: 0 });
const summaryCards: Array<{ key: keyof InvoiceCounts; label: string; color: string }> = [
  { key: "total", label: "总计", color: "#1677ff" },
  { key: "ok", label: "正常", color: "#52c41a" },
  { key: "warn", label: "警告", color: "#faad14" },
  { key: "error", label: "异常", color: "#ff4d4f" },
  { key: "duplicate", label: "重复", color: "#8c8c8c" }
];

const statusOptions: Array<{ label: string; value: string }> = [
  { label: "正常", value: "ok" },
  { label: "警告", value: "warn" },
  { label: "异常", value: "error" },
  { label: "重复", value: "duplicate" },
  { label: "正常&重复", value: "ok,duplicate" }
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
  { title: "标签", dataIndex: "tags", key: "tags" },
  { title: "状态", dataIndex: "status", key: "status" },
  { title: "上传时间", dataIndex: "uploaded_at", key: "uploaded_at" },
  { title: "操作", key: "action" }
];

const formatTime = (value: string | null) => (value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "");

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
  filters.tag = undefined;
  dateRange.value = null;
  invoiceStore.resetFilter();
  invoiceStore.loadInvoices({ invoice_no: "", status: undefined, tag: undefined, date_start: undefined, date_end: undefined });
};

const onTableChange = (pagination: { current: number; pageSize: number }) => {
  invoiceStore.loadInvoices({ page: pagination.current, page_size: pagination.pageSize });
};

const downloadCsv = async (loadingRef: typeof exporting, quoteNo: boolean, filename: string) => {
  loadingRef.value = true;
  try {
    const { data } = await exportInvoices(buildFilters(), quoteNo);
    const url = window.URL.createObjectURL(new Blob([data], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err));
  } finally {
    loadingRef.value = false;
  }
};

const onExport = () => downloadCsv(exporting, false, "invoices.csv");
const onExportQuoted = () => downloadCsv(exportingQuoted, true, "invoices_quoted.csv");

onMounted(() => {
  invoiceStore.loadInvoices({});
  refreshSummary();
  loadTags();
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

.muted {
  color: #bfbfbf;
}

.tag-manage {
  max-height: 300px;
  overflow: auto;
}

.tag-manage-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 2px 0;
}
</style>

<style>
.row-deleted td {
  color: #bfbfbf !important;
}
.row-deleted a {
  color: #bfbfbf !important;
}
</style>
