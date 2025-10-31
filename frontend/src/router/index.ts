import { createRouter, createWebHistory, RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "overview",
    component: () => import("../views/OverviewView.vue")
  },
  {
    path: "/invoices",
    name: "invoices",
    component: () => import("../views/InvoicesListView.vue")
  },
  {
    path: "/invoices/:invoiceNo",
    name: "invoice-detail",
    component: () => import("../views/InvoiceDetailView.vue"),
    props: true
  },
  {
    path: "/upload",
    name: "upload",
    component: () => import("../views/UploadView.vue")
  },
  {
    path: "/export",
    name: "export",
    component: () => import("../views/ExportView.vue")
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

export default router;
