import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    children: [
      {
        path: '',
        name: 'upload',
        component: () => import('@/views/UploadView.vue')
      },
      {
        path: 'apps',
        name: 'apps',
        component: () => import('@/views/StoredAppsView.vue')
      },
      {
        path: 'modules',
        name: 'modules',
        component: () => import('@/views/ModulesView.vue')
      },
      {
        path: 'chains',
        name: 'chains',
        component: () => import('@/views/ChainsView.vue')
      },
      {
        path: '/apps/report/:fileHash',
        name: 'AppReport',
        component: () => import('@/views/ReportView.vue'),
        props: true
      },
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router