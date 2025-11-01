<template>
  <a-layout class="app-layout">
    <a-layout-header class="app-header">
        <div class="header-left">
          <div class="logo">发票归档系统</div>
          <a-menu mode="horizontal" theme="dark" :selectedKeys="[selectedMenu]" @click="onMenuClick">
            <a-menu-item key="overview">概览</a-menu-item>
            <a-menu-item key="invoices">发票列表</a-menu-item>
            <a-menu-item key="upload">上传</a-menu-item>
            <a-menu-item key="export">导出</a-menu-item>
          </a-menu>
        </div>
        <div class="auth-controls">
          <a-space align="center" :size="8">
            <span class="auth-label">角色</span>
            <a-select :value="role" style="width: 140px" @change="onRoleChange">
              <a-select-option v-for="option in roleOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </a-select-option>
            </a-select>
            <a-input
              v-model:value="customTokenInput"
              placeholder="自定义 Token"
              allow-clear
              style="width: 220px"
            />
            <a-button type="primary" @click="applyCustomToken">应用</a-button>
            <a-button v-if="isCustomToken" @click="restorePreset">恢复预设</a-button>
          </a-space>
        </div>
    </a-layout-header>
    <a-layout>
      <a-layout-sider breakpoint="lg" collapsed-width="0" :trigger="null" class="app-sider">
        <a-menu mode="inline" :selectedKeys="[selectedMenu]" @click="onMenuClick">
          <a-menu-item key="overview">概览</a-menu-item>
          <a-menu-item key="invoices">发票列表</a-menu-item>
          <a-menu-item key="upload">上传</a-menu-item>
          <a-menu-item key="export">导出</a-menu-item>
        </a-menu>
      </a-layout-sider>
      <a-layout-content class="app-content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { useAuthStore, roleLabelMap } from "./stores/authStore";
import type { UserRole } from "./utils/authToken";
import { storeToRefs } from "pinia";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const { isCustomToken, role, roleOptions, authToken } = storeToRefs(authStore);

const selectedMenu = computed(() => {
  if (route.name === "invoice-detail") {
    return "invoices";
  }
  return String(route.name ?? "overview");
});

const onMenuClick = ({ key }: { key: string }) => {
  router.push({ name: key });
};

const customTokenInput = ref("");

const onRoleChange = (value: string) => {
  authStore.setRole(value as UserRole);
  customTokenInput.value = authToken.value;
  message.success(`已切换为 ${roleLabelMap[value as UserRole]}`);
};

const applyCustomToken = () => {
  if (!customTokenInput.value.trim()) {
    message.warning("请先输入 Token");
    return;
  }
  authStore.setCustomToken(customTokenInput.value);
  if (isCustomToken.value) {
    message.success("自定义 Token 已应用");
  } else {
    message.success("已匹配到预设 Token");
  }
};

const restorePreset = () => {
  authStore.resetToPreset();
  customTokenInput.value = authToken.value;
  message.success("已恢复当前角色的预设 Token");
};

onMounted(() => {
  authStore.initialize();
  customTokenInput.value = authToken.value;
});

watch(
  authToken,
  (next) => {
    if (customTokenInput.value !== next) {
      customTokenInput.value = next;
    }
  }
);
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.logo {
  color: #fff;
  font-size: 18px;
  font-weight: 600;
}

.auth-controls {
  display: flex;
  align-items: center;
  color: #fff;
}

.auth-label {
  color: #fff;
}

.app-sider {
  background: #fff;
}

.app-content {
  padding: 24px;
  background: #f5f7fa;
}
</style>
