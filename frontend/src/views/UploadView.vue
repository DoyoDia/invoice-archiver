<template>
  <div class="upload-view">
    <a-card title="上传发票" class="upload-card">
      <a-upload-dragger
        :file-list="fileList"
        :before-upload="handleBeforeUpload"
        :max-count="10"
        multiple
        accept="application/pdf"
        :disabled="uploading"
        @remove="handleRemove"
      >
        <p class="ant-upload-drag-icon">
          <inbox-outlined />
        </p>
        <p class="ant-upload-text">拖拽或点击选择 PDF 文件</p>
        <p class="ant-upload-hint">单文件 ≤ 100MB，页数 ≤ 100</p>
      </a-upload-dragger>

      <a-space class="actions" align="center">
        <a-button type="primary" @click="submitUpload" :loading="uploading" :disabled="fileList.length === 0">
          上传并处理
        </a-button>
        <a-button @click="clearFiles" :disabled="uploading || fileList.length === 0">清空</a-button>
      </a-space>
    </a-card>

    <a-card title="任务队列" class="mt-16">
      <a-table :columns="jobColumns" :data-source="jobs" row-key="job_id" size="small">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColorMap[record.status]">
              {{ jobStatusLabel(record.status) }}
            </a-tag>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-alert v-if="errorMessage" type="error" :message="errorMessage" show-icon class="mt-16" />
    <a-alert v-if="successMessage" type="success" :message="successMessage" show-icon class="mt-16" />
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import type { UploadProps } from "ant-design-vue";
import { message } from "ant-design-vue";
import { InboxOutlined } from "@ant-design/icons-vue";
import { uploadInvoices } from "../services/invoiceService";
import type { TaskStatus } from "../types/api";
import type { UploadFile } from "ant-design-vue/es/upload/interface";

const fileList = ref<UploadFile[]>([]);
const uploading = ref(false);
const jobs = ref<Array<{ job_id: string; file_id: number; status: TaskStatus }>>([]);
const errorMessage = ref("");
const successMessage = ref("");

const handleBeforeUpload: UploadProps["beforeUpload"] = (file) => {
  const rawFile = file as unknown as File;
  const isPdf = rawFile.type === "application/pdf";
  if (!isPdf) {
    message.error("仅支持 PDF 文件");
    return false;
  }
  const isLt100Mb = (rawFile.size || 0) / 1024 / 1024 <= 100;
  if (!isLt100Mb) {
    message.error("文件超过 100MB 限制");
    return false;
  }
  
  const uploadFile: UploadFile = {
    uid: `${Date.now()}-${Math.random()}`,
    name: rawFile.name,
    status: "done",
    size: rawFile.size,
    type: rawFile.type,
    originFileObj: rawFile as any
  };
  fileList.value = [...fileList.value, uploadFile];
  return false;
};

const handleRemove: UploadProps["onRemove"] = (file: UploadFile) => {
  fileList.value = fileList.value.filter((item: UploadFile) => item.uid !== file.uid);
};

const clearFiles = () => {
  fileList.value = [];
};

const statusColorMap: Record<TaskStatus, string> = {
  queued: "blue",
  processing: "warning",
  finished: "success",
  failed: "error",
  dead_letter: "volcano"
};

const jobStatusLabel = (status: TaskStatus) => {
  const map: Record<TaskStatus, string> = {
    queued: "排队中",
    processing: "处理中",
    finished: "完成",
    failed: "失败",
    dead_letter: "死信"
  };
  return map[status];
};

const jobColumns = [
  { title: "任务 ID", dataIndex: "job_id", key: "job_id" },
  { title: "文件 ID", dataIndex: "file_id", key: "file_id" },
  { title: "状态", dataIndex: "status", key: "status" }
];

const submitUpload = async () => {
  if (fileList.value.length === 0) {
    message.warning("请先选择文件");
    return;
  }

  uploading.value = true;
  errorMessage.value = "";
  successMessage.value = "";

  try {
    const files = fileList.value
      .map((item: UploadFile) => item.originFileObj as File)
      .filter((file): file is File => file instanceof File);
    
    if (files.length === 0) {
      throw new Error("没有有效的文件可上传");
    }
    
    const result = await uploadInvoices(files);
    jobs.value = [...result, ...jobs.value];
    successMessage.value = `已提交 ${result.length} 个任务`;
    clearFiles();
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err);
  } finally {
    uploading.value = false;
  }
};
</script>

<style scoped>
.upload-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.upload-card {
  border-radius: 8px;
}

.actions {
  margin-top: 16px;
}

.mt-16 {
  margin-top: 16px;
}
</style>
