<template>
  <div>
    <div class="toolbar">
      <el-select v-model="kindFilter" placeholder="类型" clearable style="width: 140px" @change="load">
        <el-option label="分析" value="analysis" />
        <el-option label="同步" value="sync" />
      </el-select>
      <el-select v-model="statusFilter" placeholder="状态" clearable style="width: 140px" @change="load">
        <el-option label="pending" value="pending" />
        <el-option label="running" value="running" />
        <el-option label="succeeded" value="succeeded" />
        <el-option label="failed" value="failed" />
      </el-select>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="runs" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column label="类型" width="80">
        <template #default="{ row }">{{ row.kind === 'analysis' ? '分析' : '同步' }}</template>
      </el-table-column>
      <el-table-column prop="ref_name" label="名称" />
      <el-table-column label="模式" width="90">
        <template #default="{ row }">{{ row.mode || '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" show-overflow-tooltip />
      <el-table-column prop="error" label="错误" show-overflow-tooltip />
      <el-table-column label="开始时间" width="180">
        <template #default="{ row }">{{ row.started_at || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link @click="openLogs(row)">日志</el-button>
          <el-button size="small" link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="logsVisible" :title="`运行日志 #${currentRun?.id}`" width="720px">
      <el-timeline>
        <el-timeline-item
          v-for="log in logs"
          :key="log.id"
          :timestamp="log.created_at"
          :type="logTimelineType(log.level)"
        >
          [{{ log.level }}] {{ log.message }}
        </el-timeline-item>
      </el-timeline>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listRunsApi,
  getRunApi,
  deleteRunApi,
  type TaskRun,
  type TaskRunDetail,
} from '@/api/tasks'

const runs = ref<TaskRun[]>([])
const kindFilter = ref<string | undefined>(undefined)
const statusFilter = ref<string | undefined>(undefined)
const logsVisible = ref(false)
const currentRun = ref<TaskRun | null>(null)
const logs = ref<TaskRunDetail['logs']>([])

onMounted(load)

async function load() {
  runs.value = await listRunsApi({
    kind: kindFilter.value,
    status: statusFilter.value,
    limit: 200,
  })
}

function statusType(s: string) {
  if (s === 'succeeded') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'running') return 'warning'
  return 'info'
}
function logTimelineType(level: string) {
  if (level === 'ERROR') return 'danger'
  if (level === 'WARNING') return 'warning'
  return 'primary'
}

async function openLogs(row: TaskRun) {
  currentRun.value = row
  const detail = await getRunApi(row.id)
  logs.value = detail.logs
  logsVisible.value = true
}

async function onDelete(row: TaskRun) {
  await ElMessageBox.confirm(`确认删除运行记录 #${row.id}？`, '提示', { type: 'warning' })
  await deleteRunApi(row.id)
  ElMessage.success('已删除')
  await load()
}
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
}
</style>
