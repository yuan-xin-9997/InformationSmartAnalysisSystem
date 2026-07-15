<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="openCreate">新增信息源</el-button>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="sources" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" />
      <el-table-column label="类型" width="120">
        <template #default="{ row }">{{ typeLabel(row.type) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="item_count" label="条目数" width="90" />
      <el-table-column label="最近同步" width="180">
        <template #default="{ row }">{{ row.last_sync_at || '-' }}</template>
      </el-table-column>
      <el-table-column prop="last_error" label="最近错误" show-overflow-tooltip />
      <el-table-column label="操作" width="360" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="onCheck(row.id)">检查</el-button>
          <el-button size="small" type="primary" @click="onSync(row.id)">同步</el-button>
          <el-button size="small" @click="openItems(row)">条目</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑信息源' : '新增信息源'" width="640px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type" :disabled="editing" style="width: 100%">
            <el-option v-for="t in typeSpecs" :key="t.type" :label="typeLabel(t.type)" :value="t.type" />
          </el-select>
        </el-form-item>
        <el-form-item label="配置(JSON)">
          <el-input v-model="configText" type="textarea" :rows="8" placeholder="请输入 JSON 配置" />
          <div class="hint">必填字段：{{ requiredHint }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="itemsVisible" :title="`条目 - ${currentSource?.name || ''}`" width="780px">
      <el-table :data="items" size="small" stripe>
        <el-table-column prop="title" label="标题" show-overflow-tooltip />
        <el-table-column label="已分析" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.analyzed ? 'success' : 'info'">{{ row.analyzed ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发布时间" width="170">
          <template #default="{ row }">{{ row.published_at || '-' }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listSourcesApi,
  createSourceApi,
  updateSourceApi,
  deleteSourceApi,
  checkSourceApi,
  syncSourceApi,
  listItemsApi,
  getTypesApi,
  type InfoSource,
  type InfoItemBrief,
  type SourceTypeSpec,
} from '@/api/sources'

const sources = ref<InfoSource[]>([])
const typeSpecs = ref<SourceTypeSpec[]>([])
const dialogVisible = ref(false)
const editing = ref<InfoSource | null>(null)
const form = reactive({ name: '', type: 'local_folder' })
const configText = ref('{\n  "folder_path": ""\n}')
const itemsVisible = ref(false)
const currentSource = ref<InfoSource | null>(null)
const items = ref<InfoItemBrief[]>([])

const requiredHint = computed(() => {
  const spec = typeSpecs.value.find((t) => t.type === form.type)
  return spec ? spec.required_keys.join(', ') : ''
})

onMounted(async () => {
  await load()
  typeSpecs.value = await getTypesApi()
})

async function load() {
  sources.value = await listSourcesApi()
}

function typeLabel(t: string) {
  return { website: '官方网站', local_folder: '本地文件夹', freshrss: 'FreshRSS' }[t] || t
}
function statusType(s: string) {
  if (s === 'ok') return 'success'
  if (s === 'error') return 'danger'
  return 'warning'
}

function openCreate() {
  editing.value = null
  form.name = ''
  form.type = 'local_folder'
  configText.value = '{\n  "folder_path": ""\n}'
  dialogVisible.value = true
}

function openEdit(row: InfoSource) {
  editing.value = row
  form.name = row.name
  form.type = row.type
  configText.value = JSON.stringify(row.config, null, 2)
  dialogVisible.value = true
}

async function onSave() {
  let config: Record<string, unknown>
  try {
    config = JSON.parse(configText.value)
  } catch {
    ElMessage.error('配置不是合法的 JSON')
    return
  }
  try {
    if (editing.value) {
      await updateSourceApi(editing.value.id, { name: form.name, config })
    } else {
      await createSourceApi({ name: form.name, type: form.type, config })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await load()
  } catch {
    /* toast shown by interceptor */
  }
}

async function onDelete(row: InfoSource) {
  await ElMessageBox.confirm(`确认删除信息源「${row.name}」？`, '提示', { type: 'warning' })
  await deleteSourceApi(row.id)
  ElMessage.success('已删除')
  await load()
}

async function onCheck(id: number) {
  try {
    const st = await checkSourceApi(id)
    ElMessage[st.status === 'ok' ? 'success' : 'error'](st.message || st.status)
    await load()
  } catch {
    /* handled */
  }
}

async function onSync(id: number) {
  const { run_id } = await syncSourceApi(id)
  ElMessage.success(`已提交同步，运行 ID: ${run_id}`)
  setTimeout(load, 1500)
}

async function openItems(row: InfoSource) {
  currentSource.value = row
  items.value = await listItemsApi(row.id)
  itemsVisible.value = true
}
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
}
.hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
