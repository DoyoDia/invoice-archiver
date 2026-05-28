import { createRouter, createWebHistory, RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "invoices",
    component: () => import("../views/InvoicesListView.vue")
  },
  {
    path: "/upload",
    name: "upload",
    component: () => import("../views/UploadView.vue")
  },
  {
    path: "/invoices/:invoiceNo",
    name: "invoice-detail",
    component: () => import("../views/InvoiceDetailView.vue"),
    props: true
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

export default router;
