<template>
  <main class="login-shell">
    <section class="login-brand">
      <div class="brand-mark">信</div>
      <p class="eyebrow">INFORMATION SMART ANALYSIS</p>
      <h1>让信息源<br /><span>真正被理解。</span></h1>
      <p>统一接入官方网站、本地文件夹与 FreshRSS 信息源，按需触发全量与增量智能分析。</p>
      <div class="login-points">
        <span>多源接入</span><span>增量分析</span><span>权限隔离</span>
      </div>
    </section>
    <form class="login-card" @submit.prevent="onLogin">
      <div>
        <p class="eyebrow">WELCOME BACK</p>
        <h2>登录分析中心</h2>
        <p>账号由系统管理员在 password.txt 或权限页面维护。</p>
      </div>
      <label>用户名
        <input v-model.trim="form.username" autocomplete="username" autofocus required placeholder="请输入用户名" />
      </label>
      <label>密码
        <input v-model="form.password" type="password" autocomplete="current-password" required placeholder="请输入密码" />
      </label>
      <p v-if="error" class="error">{{ error }}</p>
      <button class="primary wide" :disabled="loading">{{ loading ? '登录中…' : '进入系统' }}</button>
      <small>默认部署账号请在首次登录后立即修改</small>
    </form>
  </main>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const error = ref('')
const form = reactive({ username: '', password: '' })

async function onLogin() {
  if (!form.username || !form.password) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.login(form.username, form.password)
    router.push('/dashboard')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>
