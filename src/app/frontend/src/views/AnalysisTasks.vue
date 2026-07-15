<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="openCreate">新建分析任务</el-button>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="tasks" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" />
      <el-table-column label="分析模式" width="110">
        <template #default="{ row }">{{ modeLabel(row.config?.mode) }}</template>
      </el-table-column>
      <el-table-column label="绑定源" width="80">
        <template #default="{ row }">{{ row.sources?.length ?? 0 }}</template>
      </el-table-column>
      <el-table-column prop="description" label="说明" show-overflow-tooltip />
      <el-table-column label="操作" width="420" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openDetail(row)">源状态</el-button>
          <el-dropdown size="small" @command="(c: string) => onRun(row.id, c as 'full'|'incremental')">
            <el-button size="small" type="primary">运行分析<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="incremental">增量分析</el-dropdown-item>
                <el-dropdown-item command="full">全量分析</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" @click="goResults(row.id)">结果</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑分析任务' : '新建分析任务'" width="640px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="分析模式">
          <el-select v-model="form.mode" style="width: 100%">
            <el-option label="逐条分析(per_item)" value="per_item" />
            <el-option label="汇总分析(aggregate)" value="aggregate" />
          </el-select>
        </el-form-item>
        <el-form-item label="绑定信息源">
          <el-select v-model="form.source_ids" multiple style="width: 100%" placeholder="选择信息源">
            <el-option v-for="s in allSources" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="高级配置">
          <el-input v-model="configText" type="textarea" :rows="4" placeholder='可留空，默认逐条分析。例如 {"mode":"per_item","max_items_per_source":50}' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="信息源状态" width="720px">
      <el-table :data="detailSources" size="small" stripe>
        <el-table-column prop="source_name" label="信息源" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.source_status)" size="small">{{ row.source_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="item_count" label="条目数" width="80" />
        <el-table-column label="水位线(item_id)" width="120">
          <template #default="{ row }">{{ row.last_analyzed_item_id ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="最近分析时间">
          <template #default="{ row }">{{ row.last_analyzed_at || '-' }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { listSourcesApi, type InfoSource } from '@/api/sources'
import {
  listTasksApi,
  createTaskApi,
  updateTaskApi,
  deleteTaskApi,
  runTaskApi,
  getTaskApi,
  type AnalysisTaskDetail,
  type TaskSourceOut,
} from '@/api/tasks'

const router = useRouter()
const tasks = ref<AnalysisTaskDetail[]>([])
const allSources = ref<InfoSource[]>([])
const dialogVisible = ref(false)
const editing = ref<AnalysisTaskDetail | null>(null)
const form = reactive({ name: '', description: '', mode: 'per_item', source_ids: [] as number[] })
const configText = ref('')
const detailVisible = ref(false)
const detailSources = ref<TaskSourceOut[]>([])

onMounted(async () => {
  await load()
  allSources.value = await listSourcesApi()
})

async function load() {
  tasks.value = await listTasksApi()
}

function modeLabel(m?: string) {
  return m === 'aggregate' ? '汇总分析' : '逐条分析'
}
function statusType(s: string) {
  if (s === 'ok') return 'success'
  if (s === 'error') return 'danger'
  return 'warning'
}

function openCreate() {
  editing.value = null
  form.name = ''
  form.description = ''
  form.mode = 'per_item'
  form.source_ids = []
  configText.value = ''
  dialogVisible.value = true
}

function openEdit(row: AnalysisTaskDetail) {
  editing.value = row
  form.name = row.name
  form.description = row.description
  form.mode = (row.config?.mode as string) || 'per_item'
  form.source_ids = row.sources.map((s) => s.source_id)
  configText.value = JSON.stringify(row.config || {}, null, 2)
  dialogVisible.value = true
}

async function onSave() {
  let config: Record<string, unknown> = { mode: form.mode }
  if (configText.value.trim()) {
    try {
      config = JSON.parse(configText.value)
    } catch {
      ElMessage.error('高级配置不是合法的 JSON')
      return
    }
  }
  config.mode = form.mode
  try {
    if (editing.value) {
      await updateTaskApi(editing.value.id, {
        name: form.name,
        description: form.description,
        config,
        source_ids: form.source_ids,
      })
    } else {
      await createTaskApi({
        name: form.name,
        description: form.description,
        config,
        source_ids: form.source_ids,
      })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await load()
  } catch {
    /* handled */
  }
}

async function onDelete(row: AnalysisTaskDetail) {
  await ElMessageBox.confirm(`确认删除分析任务「${row.name}」？`, '提示', { type: 'warning' })
  await deleteTaskApi(row.id)
  ElMessage.success('已删除')
  await load()
}

async function onRun(id: number, mode: 'full' | 'incremental') {
  const { run_id } = await runTaskApi(id, mode)
  ElMessage.success(`已提交${mode === 'full' ? '全量' : '增量'}分析，运行 ID: ${run_id}`)
}

async function openDetail(row: AnalysisTaskDetail) {
  const detail = await getTaskApi(row.id)
  detailSources.value = detail.sources
  detailVisible.value = true
}

function goResults(taskId: number) {
  router.push({ path: '/analysis-result', query: { task_id: taskId } })
}
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
}
</style>
