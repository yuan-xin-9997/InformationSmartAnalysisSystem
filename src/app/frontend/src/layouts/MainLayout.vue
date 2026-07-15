<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">信息智能分析系统</div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#1f2d3d"
        text-color="#bfcbd9"
        active-text-color="#409eff"
      >
        <el-menu-item
          v-for="item in visibleMenus"
          :key="item.path"
          :index="item.path"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-title">{{ currentTitle }}</div>
        <div class="header-user">
          <span>{{ auth.user?.username }}（{{ auth.isAdmin ? '管理员' : '普通用户' }}）</span>
          <el-button link type="primary" @click="onLogout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataLine,
  Files,
  Document,
  Memo,
  List,
  Setting,
  User,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const allMenus = [
  { path: '/dashboard', page: 'dashboard', title: '概览', icon: DataLine },
  { path: '/info-sources', page: 'info_sources', title: '信息源管理', icon: Files },
  { path: '/analysis-tasks', page: 'analysis_tasks', title: '分析任务', icon: Document },
  { path: '/analysis-result', page: 'analysis_result', title: '分析结果', icon: Memo },
  { path: '/task-center', page: 'task_center', title: '任务中心', icon: List },
  { path: '/permission', page: 'permission', title: '权限管理', icon: User },
  { path: '/system-config', page: 'system_config', title: '系统配置', icon: Setting },
]

const visibleMenus = computed(() =>
  allMenus.filter((m) => auth.pages.includes(m.page)),
)

const activeMenu = computed(() => route.path)
const currentTitle = computed(() => (route.meta.title as string) || '')

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout {
  height: 100vh;
}
.aside {
  background-color: #1f2d3d;
}
.logo {
  height: 60px;
  line-height: 60px;
  text-align: center;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  border-bottom: 1px solid #2c3e50;
}
.aside :deep(.el-menu) {
  border-right: none;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: #fff;
  border-bottom: 1px solid #e6e6e6;
}
.header-title {
  font-size: 16px;
  font-weight: 600;
}
.header-user {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #606266;
}
.main {
  background-color: #f0f2f5;
}
</style>
