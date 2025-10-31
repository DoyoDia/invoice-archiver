<template>
  <a-layout class="app-layout">
    <a-layout-header class="app-header">
      <div class="logo">发票归档系统</div>
      <a-menu mode="horizontal" theme="dark" :selectedKeys="[selectedMenu]" @click="onMenuClick">
        <a-menu-item key="overview">概览</a-menu-item>
        <a-menu-item key="invoices">发票列表</a-menu-item>
        <a-menu-item key="upload">上传</a-menu-item>
        <a-menu-item key="export">导出</a-menu-item>
      </a-menu>
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
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

const selectedMenu = computed(() => {
  if (route.name === "invoice-detail") {
    return "invoices";
  }
  return String(route.name ?? "overview");
});

const onMenuClick = ({ key }: { key: string }) => {
  router.push({ name: key });
};
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

.logo {
  color: #fff;
  font-size: 18px;
  font-weight: 600;
}

.app-sider {
  background: #fff;
}

.app-content {
  padding: 24px;
  background: #f5f7fa;
}
</style>
