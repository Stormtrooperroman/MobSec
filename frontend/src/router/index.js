import { createRouter, createWebHistory } from 'vue-router';

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    children: [
      {
        path: '',
        name: 'upload',
        component: () => import('@/views/UploadView.vue'),
        meta: {
          title: 'Upload Applications - MobSec',
        },
      },
      {
        path: 'apps',
        name: 'apps',
        component: () => import('@/views/StoredAppsView.vue'),
        meta: {
          title: 'Stored Applications - MobSec',
        },
      },
      {
        path: 'modules',
        name: 'modules',
        component: () => import('@/views/ModulesView.vue'),
        meta: {
          title: 'Modules - MobSec',
        },
      },
      {
        path: 'chains',
        name: 'chains',
        component: () => import('@/views/ChainsView.vue'),
        meta: {
          title: 'Analysis Chains - MobSec',
        },
      },
      {
        path: '/apps/report/:fileHash',
        name: 'AppReport',
        component: () => import('@/views/ReportView.vue'),
        props: true,
        meta: {
          title: 'Application Report - MobSec',
        },
      },
      {
        path: '/settings',
        name: 'settings',
        component: () => import('@/views/SettingsView.vue'),
        meta: {
          title: 'Settings - MobSec',
        },
      },
      {
        path: '/dynamic-testing',
        name: 'Dynamic Testing',
        component: () => import('@/views/DynamicTesting.vue'),
        meta: {
          title: 'Dynamic Testing - MobSec',
        },
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to, from, next) => {
  if (to.meta.title) {
    document.title = to.meta.title;
  } else {
    document.title = 'MobSec';
  }
  next();
});

export default router;
