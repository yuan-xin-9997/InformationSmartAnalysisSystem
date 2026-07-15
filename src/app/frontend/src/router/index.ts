import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { page: 'dashboard', title: '概览' } },
      { path: 'info-sources', component: () => import('@/views/InfoSources.vue'), meta: { page: 'info_sources', title: '信息源管理' } },
      { path: 'analysis-tasks', component: () => import('@/views/AnalysisTasks.vue'), meta: { page: 'analysis_tasks', title: '分析任务' } },
      { path: 'analysis-result', component: () => import('@/views/AnalysisResult.vue'), meta: { page: 'analysis_result', title: '分析结果' } },
      { path: 'task-center', component: () => import('@/views/TaskCenter.vue'), meta: { page: 'task_center', title: '任务中心' } },
      { path: 'permission', component: () => import('@/views/Permission.vue'), meta: { page: 'permission', title: '权限管理' } },
      { path: 'system-config', component: () => import('@/views/SystemConfig.vue'), meta: { page: 'system_config', title: '系统配置' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (to.path === '/login' && auth.token) return '/dashboard'
    return true
  }
  if (!auth.token) return '/login'
  if (!auth.user) {
    await auth.fetchMe()
    if (!auth.token) return '/login'
  }
  const page = to.meta.page as string | undefined
  if (page && !auth.pages.includes(page)) {
    // No access to this page -> send to dashboard (or login if even that's missing).
    return auth.pages.includes('dashboard') ? '/dashboard' : '/login'
  }
  return true
})

export default router
