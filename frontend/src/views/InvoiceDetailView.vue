<template>
  <div class="invoice-detail">
    <a-breadcrumb>
      <a-breadcrumb-item>
        <router-link :to="{ name: 'invoices' }">发票列表</router-link>
      </a-breadcrumb-item>
      <a-breadcrumb-item>{{ invoiceNo }}</a-breadcrumb-item>
    </a-breadcrumb>

    <a-spin :spinning="loading" class="mt-16">
      <template v-if="detail">
        <a-row :gutter="16">
          <a-col :xs="24" :lg="12">
            <a-card title="基础信息" class="detail-card">
              <a-descriptions bordered :column="1" size="small">
                <a-descriptions-item label="发票号">{{ detail.invoice.invoice_no }}</a-descriptions-item>
                <a-descriptions-item label="类型">{{ detail.invoice.invoice_type }}</a-descriptions-item>
                <a-descriptions-item label="开票日期">{{ detail.invoice.invoice_date }}</a-descriptions-item>
                <a-descriptions-item label="状态">
                  <a-tag v-if="detail.invoice.deleted" color="default">删除</a-tag>
                  <a-tag v-else :color="statusColorMap[detail.invoice.status]">
                    {{ statusLabelMap[detail.invoice.status] }}
                  </a-tag>
                </a-descriptions-item>
                <a-descriptions-item label="标签">
                  <a-select
                    v-model:value="editTags"
                    mode="tags"
                    placeholder="选择或输入标签（回车创建）"
                    style="width: 100%"
                    :options="tagOptions"
                    @blur="saveTags"
                  />
                </a-descriptions-item>
              </a-descriptions>
            </a-card>
          </a-col>
          <a-col :xs="24" :lg="12">
            <a-card title="金额" class="detail-card">
              <a-descriptions bordered :column="1" size="small">
                <a-descriptions-item label="合计金额">{{ detail.invoice.totals.amount }}</a-descriptions-item>
                <a-descriptions-item label="合计税额">{{ detail.invoice.totals.tax }}</a-descriptions-item>
                <a-descriptions-item label="价税合计">{{ detail.invoice.totals.grand }}</a-descriptions-item>
              </a-descriptions>
            </a-card>
          </a-col>
        </a-row>

        <a-row :gutter="16" class="mt-16">
          <a-col :xs="24" :lg="12">
            <a-card title="购买方" class="detail-card">
              <a-descriptions bordered :column="1" size="small">
                <a-descriptions-item label="名称">{{ detail.invoice.buyer.name }}</a-descriptions-item>
                <a-descriptions-item label="纳税人识别号">{{ detail.invoice.buyer.tax_id }}</a-descriptions-item>
              </a-descriptions>
            </a-card>
          </a-col>
          <a-col :xs="24" :lg="12">
            <a-card title="销售方" class="detail-card">
              <a-descriptions bordered :column="1" size="small">
                <a-descriptions-item label="名称">{{ detail.invoice.seller.name }}</a-descriptions-item>
                <a-descriptions-item label="纳税人识别号">{{ detail.invoice.seller.tax_id }}</a-descriptions-item>
              </a-descriptions>
            </a-card>
          </a-col>
        </a-row>

        <a-card title="行项目" class="mt-16 detail-card">
          <a-table
            :data-source="detail.line_items"
            :columns="lineColumns"
            :pagination="false"
            row-key="item_name"
            size="small"
          />
        </a-card>

        <a-card v-if="detail.invoice.notes" title="校验提示" class="mt-16 detail-card">
          <a-alert type="warning" :message="detail.invoice.notes" show-icon />
        </a-card>

        <a-card title="解析结果 JSON" class="mt-16 detail-card">
          <a-collapse>
            <a-collapse-panel key="raw" header="展开查看 JSON">
              <pre class="json-viewer">{{ formattedJson }}</pre>
            </a-collapse-panel>
          </a-collapse>
        </a-card>

        <div class="actions">
          <a-button :danger="!detail.invoice.deleted" @click="onToggleDeleted" :loading="togglingDeleted">
            {{ detail.invoice.deleted ? "取消删除" : "标记删除" }}
          </a-button>
          <a-button type="primary" @click="onDownloadSource" :loading="downloading">
            下载原始文件
          </a-button>
        </div>
      </template>
    </a-spin>

    <a-alert v-if="errorMessage" type="error" :message="errorMessage" show-icon class="mt-16" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { message } from "ant-design-vue";
import {
  downloadSourceFile,
  fetchInvoiceDetail,
  fetchTags,
  setInvoiceDeleted,
  setInvoiceTags
} from "../services/invoiceService";
import type { InvoiceDetail, InvoiceStatus } from "../types/invoice";

const props = defineProps<{ invoiceNo: string }>();
const route = useRoute();
const invoiceNo = props.invoiceNo ?? (route.params.invoiceNo as string);

const detail = ref<InvoiceDetail | null>(null);
const loading = ref(false);
const downloading = ref(false);
const togglingDeleted = ref(false);
const errorMessage = ref("");

const editTags = ref<string[]>([]);
const tagOptions = ref<{ value: string; label: string }[]>([]);

const statusLabelMap: Record<InvoiceStatus, string> = {
  ok: "正常",
  warn: "警告",
  error: "异常",
  duplicate: "重复"
};

const statusColorMap: Record<InvoiceStatus, string> = {
  ok: "success",
  warn: "warning",
  error: "error",
  duplicate: "default"
};

const lineColumns = [
  { title: "项目名称", dataIndex: "item_name", key: "item_name" },
  { title: "规格型号", dataIndex: "spec_model", key: "spec_model" },
  { title: "数量", dataIndex: "quantity", key: "quantity" },
  { title: "单价", dataIndex: "unit_price", key: "unit_price" },
  { title: "金额", dataIndex: "amount", key: "amount" },
  { title: "税率", dataIndex: "tax_rate", key: "tax_rate" },
  { title: "税额", dataIndex: "tax_amount", key: "tax_amount" }
];

const loadDetail = async () => {
  loading.value = true;
  errorMessage.value = "";
  try {
    detail.value = await fetchInvoiceDetail(invoiceNo);
    editTags.value = [...detail.value.invoice.tags];
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
};

const saveTags = async () => {
  if (!detail.value) return;
  const current = detail.value.invoice.tags;
  const next = editTags.value;
  if (current.length === next.length && current.every((t) => next.includes(t))) return;
  try {
    await setInvoiceTags(invoiceNo, next);
    detail.value.invoice.tags = [...next];
    message.success("标签已保存");
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err));
    editTags.value = [...current];
  }
};

const onToggleDeleted = async () => {
  if (!detail.value) return;
  togglingDeleted.value = true;
  try {
    const next = !detail.value.invoice.deleted;
    await setInvoiceDeleted(invoiceNo, next);
    detail.value.invoice.deleted = next;
    message.success(next ? "已标记删除" : "已取消删除");
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err));
  } finally {
    togglingDeleted.value = false;
  }
};

const formattedJson = computed(() =>
  detail.value?.raw_json ? JSON.stringify(detail.value.raw_json, null, 2) : "暂无数据"
);

const onDownloadSource = async () => {
  if (!detail.value) return;
  downloading.value = true;
  try {
    const response = await downloadSourceFile(detail.value.invoice.source_file_id);
    const blob = new Blob([response.data], { type: "application/pdf" });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${detail.value.invoice.invoice_no}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err);
  } finally {
    downloading.value = false;
  }
};

onMounted(async () => {
  await loadDetail();
  try {
    tagOptions.value = (await fetchTags()).map((t) => ({ value: t.name, label: t.name }));
  } catch {
    /* 标签加载失败不影响详情 */
  }
});
</script>

<style scoped>
.invoice-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-card {
  border-radius: 8px;
}

.mt-16 {
  margin-top: 16px;
}

.actions {
  margin-top: 24px;
  display: flex;
  justify-content: flex-end;
}

.json-viewer {
  background: #0f172a;
  color: #e2e8f0;
  padding: 16px;
  border-radius: 6px;
  overflow: auto;
  max-height: 320px;
}
</style>
