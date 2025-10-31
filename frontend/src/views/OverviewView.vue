<template>
  <div class="overview">
    <a-row :gutter="16">
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :loading="loadingCounts" class="metric-card">
          <a-statistic title="总票数" :value="invoiceCounts.total" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :loading="loadingCounts" class="metric-card status-ok">
          <a-statistic title="正常" :value="invoiceCounts.ok" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :loading="loadingCounts" class="metric-card status-warn">
          <a-statistic title="警告" :value="invoiceCounts.warn" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :loading="loadingCounts" class="metric-card status-error">
          <a-statistic title="异常" :value="invoiceCounts.error" />
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="16" class="mt-24">
      <a-col :xs="24" :lg="12">
        <a-card title="近况" :loading="loadingHealth">
          <a-descriptions bordered size="small" :column="1">
            <a-descriptions-item label="系统状态">{{ healthStatus.status }}</a-descriptions-item>
            <a-descriptions-item label="版本">{{ healthStatus.version }}</a-descriptions-item>
            <a-descriptions-item label="更新时间">{{ formattedTimestamp }}</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-col>
      <a-col :xs="24" :lg="12">
        <a-card title="依赖服务" :loading="loadingHealth">
          <a-list :data-source="dependencyList" bordered>
            <template #renderItem="{ item }">
              <a-list-item>
                <div class="dependency-row">
                  <span class="dependency-name">{{ item[0] }}</span>
                  <span class="dependency-status">{{ item[1] }}</span>
                </div>
              </a-list-item>
            </template>
          </a-list>
        </a-card>
      </a-col>
    </a-row>

    <a-alert v-if="errorMessage" type="error" :message="errorMessage" show-icon class="mt-24" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import dayjs from "dayjs";
import { fetchHealth } from "../services/systemService";
import { fetchInvoiceCounts } from "../services/invoiceService";

const invoiceCounts = reactive({ total: 0, ok: 0, warn: 0, error: 0, duplicate: 0, conflict_duplicate: 0 });
const healthStatus = reactive({ status: "-", version: "-", timestamp: "", dependencies: {} as Record<string, string> });
const loadingCounts = ref(false);
const loadingHealth = ref(false);
const errorMessage = ref("");

const loadCounts = async () => {
  loadingCounts.value = true;
  try {
    const counts = await fetchInvoiceCounts();
    Object.assign(invoiceCounts, counts);
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingCounts.value = false;
  }
};

const loadHealth = async () => {
  loadingHealth.value = true;
  try {
    const health = await fetchHealth();
    Object.assign(healthStatus, health);
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingHealth.value = false;
  }
};

onMounted(() => {
  loadCounts();
  loadHealth();
});

const formattedTimestamp = computed(() =>
  healthStatus.timestamp ? dayjs(healthStatus.timestamp).format("YYYY-MM-DD HH:mm:ss") : "-"
);

const dependencyList = computed(() => Object.entries(healthStatus.dependencies || {}));

</script>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.metric-card {
  border-radius: 8px;
}

.status-ok {
  border-left: 4px solid #52c41a;
}

.status-warn {
  border-left: 4px solid #faad14;
}

.status-error {
  border-left: 4px solid #ff4d4f;
}

.mt-24 {
  margin-top: 24px;
}

.dependency-row {
  display: flex;
  justify-content: space-between;
}

.dependency-name {
  font-weight: 500;
}

.dependency-status {
  text-transform: capitalize;
}
</style>
