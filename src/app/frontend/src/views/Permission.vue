<template>
  <div>
    <div class="toolbar">
      <div class="stats"><strong>{{ users.length }}</strong><span>个系统用户</span></div>
      <button @click="load">刷新</button>
    </div>
    <div class="panel">
      <table>
        <thead>
          <tr><th>用户</th><th>角色</th><th>可访问页面</th><th>创建时间</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td><strong>{{ u.username }}</strong></td>
            <td><span :class="['pill', u.role === 'admin' ? 'error' : '']">{{ u.role === 'admin' ? '管理员' : '普通用户' }}</span></td>
            <td><div class="tags"><span v-for="p in pageKeys(u)" :key="p">{{ pageLabel(p) }}</span></div></td>
            <td>{{ u.created_at }}</td>
            <td>
              <div class="actions">
                <button :disabled="u.role === 'admin'" @click="openConfig(u)">配置权限</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="muted" style="margin-top:12px;font-size:12px">用户与角色来源于 data/password.txt，修改后下次登录自动同步。管理员默认拥有全部页面权限。</p>

    <div v-if="dialogVisible" class="modal" @click.self="dialogVisible = false">
      <form class="modal-card" @submit.prevent="onSave">
        <div class="modal-head">
          <div><p class="eyebrow">ACCESS CONTROL</p><h2>配置权限 - {{ currentUser?.username }}</h2></div>
          <button type="button" @click="dialogVisible = false">×</button>
        </div>
        <fieldset>
          <legend>可访问页面</legend>
          <label v-for="p in pages" :key="p.key" class="check">
            <input type="checkbox" :disabled="!p.grantable" :checked="selected.includes(p.key)" @change="toggle(p.key)" />
            {{ p.label }}（{{ p.key }}）
          </label>
        </fieldset>
        <div class="modal-actions">
          <button type="button" @click="dialogVisible = false">取消</button>
          <button class="primary">保存</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { showToast } from '@/composables/toast'
import { listUsersApi, listPagesApi, getPermissionsApi, setPermissionsApi, type UserOut, type PageDefinition } from '@/api/users'

const users = ref<UserOut[]>([])
const pages = ref<PageDefinition[]>([])
const dialogVisible = ref(false)
const currentUser = ref<UserOut | null>(null)
const selected = ref<string[]>([])

onMounted(async () => {
  await load()
  pages.value = await listPagesApi()
})

async function load() {
  users.value = await listUsersApi()
}

function pageLabel(key: string) {
  const map: Record<string, string> = {
    dashboard: '概览', info_sources: '信息源', analysis_tasks: '分析任务',
    analysis_result: '分析结果', task_center: '任务中心', permission: '权限管理', system_config: '系统配置',
  }
  return map[key] || key
}
function pageKeys(u: UserOut) {
  return u.role === 'admin' ? pages.value.map((p) => p.key) : []
}

async function openConfig(u: UserOut) {
  currentUser.value = u
  selected.value = await getPermissionsApi(u.id)
  dialogVisible.value = true
}
function toggle(key: string) {
  selected.value = selected.value.includes(key)
    ? selected.value.filter((k) => k !== key)
    : [...selected.value, key]
}
async function onSave() {
  if (!currentUser.value) return
  await setPermissionsApi(currentUser.value.id, selected.value)
  showToast('已保存')
  dialogVisible.value = false
}
</script>
