<template>
  <div>
    <div class="toolbar">
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="users" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column label="角色" width="120">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : ''">{{ row.role === 'admin' ? '管理员' : '普通用户' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ row.created_at }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" :disabled="row.role === 'admin'" @click="openConfig(row)">配置权限</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="hint">用户与角色来源于 data/password.txt，修改该文件后下次登录自动同步。管理员默认拥有全部页面权限。</div>

    <el-dialog v-model="dialogVisible" :title="`配置权限 - ${currentUser?.username}`" width="560px">
      <el-checkbox-group v-model="selected">
        <div v-for="p in pages" :key="p.key" class="perm-item">
          <el-checkbox :label="p.key" :disabled="!p.grantable">{{ p.label }}（{{ p.key }}）</el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listUsersApi,
  listPagesApi,
  getPermissionsApi,
  setPermissionsApi,
  type UserOut,
  type PageDefinition,
} from '@/api/users'

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

async function openConfig(row: UserOut) {
  currentUser.value = row
  selected.value = await getPermissionsApi(row.id)
  dialogVisible.value = true
}

async function onSave() {
  if (!currentUser.value) return
  await setPermissionsApi(currentUser.value.id, selected.value)
  ElMessage.success('已保存')
  dialogVisible.value = false
}
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}
.perm-item {
  margin: 6px 0;
}
.hint {
  margin-top: 12px;
  color: #909399;
  font-size: 12px;
}
</style>
