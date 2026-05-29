<template>
  <div class="upload-view">
    <a-card title="上传发票" class="upload-card">
      <a-upload-dragger
        :file-list="fileList"
        :before-upload="handleBeforeUpload"
        multiple
        accept="application/pdf"
        :disabled="uploading"
        @remove="handleRemove"
      >
        <p class="ant-upload-drag-icon"><inbox-outlined /></p>
        <p class="ant-upload-text">拖拽或点击选择 PDF 文件</p>
        <p class="ant-upload-hint">单文件 ≤ 50MB，页数 ≤ 50</p>
      </a-upload-dragger>

      <div class="tag-row">
        <span class="tag-label">统一标签：</span>
        <a-select
          v-model:value="selectedTags"
          mode="tags"
          placeholder="选择或输入标签（回车创建），将应用到本批所有发票"
          :options="tagOptions"
          style="flex: 1"
          :disabled="uploading"
        />
      </div>

      <a-space class="actions">
        <a-button type="primary" @click="submitUpload" :loading="uploading" :disabled="fileList.length === 0">
          上传并解析
        </a-button>
        <a-button @click="clearFiles" :disabled="uploading || fileList.length === 0">清空</a-button>
      </a-space>
    </a-card>

    <a-card v-if="results.length" title="解析结果" class="mt-16">
      <a-table :columns="resultColumns" :data-source="results" row-key="_key" size="small" :pagination="false">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'invoice_no'">
            <router-link
              v-if="record.invoice_no"
              :to="{ name: 'invoice-detail', params: { invoiceNo: record.invoice_no } }"
            >
              {{ record.invoice_no }}
            </router-link>
            <span v-else>-</span>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import type { UploadProps } from "ant-design-vue";
import { message } from "ant-design-vue";
import { InboxOutlined } from "@ant-design/icons-vue";
import type { UploadFile } from "ant-design-vue/es/upload/interface";
import { fetchTags, uploadInvoices } from "../services/invoiceService";
import type { IngestResult } from "../types/invoice";

type ResultRow = IngestResult & { _key: string };

const fileList = ref<UploadFile[]>([]);
const uploading = ref(false);
const results = ref<ResultRow[]>([]);
const selectedTags = ref<string[]>([]);
const tagOptions = ref<{ value: string; label: string }[]>([]);
let keySeq = 0;

onMounted(async () => {
  try {
    tagOptions.value = (await fetchTags()).map((t) => ({ value: t.name, label: t.name }));
  } catch {
    /* 标签加载失败不影响上传 */
  }
});

const handleBeforeUpload: UploadProps["beforeUpload"] = (file) => {
  const rawFile = file as unknown as File;
  if (rawFile.type !== "application/pdf") {
    message.error("仅支持 PDF 文件");
    return false;
  }
  if ((rawFile.size || 0) / 1024 / 1024 > 50) {
    message.error("文件超过 50MB 限制");
    return false;
  }
  fileList.value = [
    ...fileList.value,
    {
      uid: `${Date.now()}-${Math.random()}`,
      name: rawFile.name,
      status: "done",
      size: rawFile.size,
      type: rawFile.type,
      originFileObj: rawFile as any
    }
  ];
  return false;
};

const handleRemove: UploadProps["onRemove"] = (file) => {
  fileList.value = fileList.value.filter((item) => item.uid !== file.uid);
};

const clearFiles = () => {
  fileList.value = [];
};

const statusColor = (status: string) =>
  ({ ok: "success", warn: "warning", error: "error", duplicate: "default", failed: "volcano" }[status] ?? "default");
const statusLabel = (status: string) =>
  ({ ok: "正常", warn: "警告", error: "异常", duplicate: "重复", failed: "失败" }[status] ?? status);

const resultColumns = [
  { title: "文件 ID", dataIndex: "file_id", key: "file_id" },
  { title: "发票号", dataIndex: "invoice_no", key: "invoice_no" },
  { title: "状态", dataIndex: "status", key: "status" },
  { title: "错误", dataIndex: "error", key: "error" }
];

const submitUpload = async () => {
  if (fileList.value.length === 0) {
    message.warning("请先选择文件");
    return;
  }
  uploading.value = true;
  try {
    const files = fileList.value
      .map((item) => item.originFileObj as File)
      .filter((file): file is File => file instanceof File);
    const result = await uploadInvoices(files, selectedTags.value);
    const stamped = result.map((r) => ({ ...r, _key: `r${keySeq++}` }));
    results.value = [...stamped, ...results.value];
    message.success(`已处理 ${files.length} 个文件，共 ${result.length} 张发票`);
    clearFiles();
  } catch (err) {
    message.error(err instanceof Error ? err.message : String(err));
  } finally {
    uploading.value = false;
  }
};
</script>

<style scoped>
.upload-view {
  display: flex;
  flex-direction: column;
}

.upload-card {
  border-radius: 8px;
}

.tag-row {
  display: flex;
  align-items: center;
  margin-top: 16px;
}

.tag-label {
  white-space: nowrap;
}

.actions {
  margin-top: 16px;
}

.mt-16 {
  margin-top: 16px;
}
</style>
