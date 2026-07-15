<template>
  <div class="app-shell">
    <aside>
      <div class="logo">
        <div class="brand-mark small">信</div>
        <div><strong>信息智能分析</strong><small>ISAS</small></div>
      </div>
      <nav>
        <button
          v-for="item in visibleMenus"
          :key="item.path"
          :class="{ active: activeMenu === item.path }"
          @click="go(item.path)"
        >
          <span>{{ item.icon }}</span>{{ item.title }}
        </button>
      </nav>
      <div class="account">
        <div class="avatar">{{ (auth.user?.username || '?').slice(0, 1).toUpperCase() }}</div>
        <div>
          <strong>{{ auth.user?.username }}</strong>
          <small>{{ auth.isAdmin ? '管理员' : '普通用户' }}</small>
        </div>
        <button title="退出" @click="onLogout">↗</button>
      </div>
    </aside>

    <section class="workspace">
      <header>
        <div>
          <p class="eyebrow">INFORMATION SMART ANALYSIS</p>
          <h1>{{ currentTitle[0] }}</h1>
          <p>{{ currentTitle[1] }}</p>
        </div>
        <div class="header-status" :class="{ down: !serviceOk }">
          <i></i>{{ serviceOk ? '服务运行中' : '服务异常' }}
        </div>
      </header>
      <section class="content">
        <router-view />
      </section>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import request from '@/api/request'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const serviceOk = ref(true)

const allMenus = [
  { path: '/dashboard', page: 'dashboard', icon: '概', title: '概览' },
  { path: '/info-sources', page: 'info_sources', icon: '源', title: '信息源管理' },
  { path: '/analysis-tasks', icon: '析', page: 'analysis_tasks', title: '分析任务' },
  { path: '/analysis-result', icon: '果', page: 'analysis_result', title: '分析结果' },
  { path: '/task-center', icon: '务', page: 'task_center', title: '任务中心' },
  { path: '/permission', icon: '权', page: 'permission', title: '权限管理' },
  { path: '/system-config', icon: '置', page: 'system_config', title: '系统配置' },
]

const pageMeta: Record<string, [string, string]> = {
  dashboard: ['概览', '信息源、分析任务与最近运行的整体情况'],
  info_sources: ['信息源管理', '添加与管理官方网站、本地文件夹、FreshRSS 信息源'],
  analysis_tasks: ['分析任务', '绑定信息源并触发全量或增量智能分析'],
  analysis_result: ['分析结果', '查看大模型逐条与汇总分析产出'],
  task_center: ['任务中心', '查看同步与分析任务运行状态及日志'],
  permission: ['权限管理', '维护用户角色与可访问页面'],
  system_config: ['系统配置', '查看运行配置（敏感字段已脱敏）'],
}

const visibleMenus = computed(() => allMenus.filter((m) => auth.pages.includes(m.page)))
const activeMenu = computed(() => route.path)
const currentTitle = computed(() => {
  const page = (route.meta.page as string) || 'dashboard'
  return pageMeta[page] || ['', '']
})

function go(path: string) {
  router.push(path)
}

function onLogout() {
  auth.logout()
  router.push('/login')
}

onMounted(async () => {
  try {
    await request.get('/api/health')
    serviceOk.value = true
  } catch {
    serviceOk.value = false
  }
})
</script>
