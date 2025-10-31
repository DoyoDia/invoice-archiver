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
                  <a-tag :color="statusColorMap[detail.invoice.status]">
                    {{ statusLabelMap[detail.invoice.status] }}
                  </a-tag>
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

        <a-card title="异常记录" class="mt-16 detail-card">
          <a-empty v-if="detail.anomalies.length === 0" description="暂无异常" />
          <a-list v-else :data-source="detail.anomalies" bordered>
            <template #renderItem="{ item }">
              <a-list-item>
                <div class="anomaly-item">
                  <span :class="['severity', `severity-${item.severity}`]">{{ item.code }}</span>
                  <span class="message">{{ item.message }}</span>
                  <span class="field">{{ item.field_path }}</span>
                </div>
              </a-list-item>
            </template>
          </a-list>
        </a-card>

        <a-card title="原始 OCR" class="mt-16 detail-card">
          <a-collapse>
            <a-collapse-panel key="raw" header="展开查看 JSON">
              <pre class="json-viewer">{{ formattedJson }}</pre>
            </a-collapse-panel>
          </a-collapse>
        </a-card>

        <div class="actions">
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
import { fetchInvoiceDetail, downloadSourceFile } from "../services/invoiceService";
import type { InvoiceDetail, InvoiceStatus } from "../types/invoice";

const props = defineProps<{ invoiceNo: string }>();
const route = useRoute();
const invoiceNo = props.invoiceNo ?? (route.params.invoiceNo as string);

const detail = ref<InvoiceDetail | null>(null);
const loading = ref(false);
const downloading = ref(false);
const errorMessage = ref("");

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
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
};

const formattedJson = computed(() =>
  detail.value?.raw_ocr_json ? JSON.stringify(detail.value.raw_ocr_json, null, 2) : "暂无数据"
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

onMounted(() => {
  loadDetail();
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

.anomaly-item {
  display: grid;
  grid-template-columns: 120px 1fr 200px;
  gap: 12px;
  align-items: center;
}

.severity {
  font-weight: 600;
}

.severity-info {
  color: #1677ff;
}

.severity-warn {
  color: #faad14;
}

.severity-error {
  color: #ff4d4f;
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
