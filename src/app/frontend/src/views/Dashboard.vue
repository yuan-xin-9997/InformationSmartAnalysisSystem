<template>
  <div class="dashboard">
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card>
          <div class="stat-num">{{ sources.length }}</div>
          <div class="stat-label">信息源</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <div class="stat-num">{{ tasks.length }}</div>
          <div class="stat-label">分析任务</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <div class="stat-num">{{ runs.length }}</div>
          <div class="stat-label">最近任务运行</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="recent">
      <template #header>最近任务运行</template>
      <el-table :data="runs.slice(0, 10)" size="small" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="类型">
          <template #default="{ row }">{{ kindLabel(row.kind) }}</template>
        </el-table-column>
        <el-table-column prop="ref_name" label="名称" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" show-overflow-tooltip />
        <el-table-column label="开始时间" width="180">
          <template #default="{ row }">{{ row.started_at || '-' }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listSourcesApi, type InfoSource } from '@/api/sources'
import { listTasksApi, listRunsApi, type AnalysisTask, type TaskRun } from '@/api/tasks'

const sources = ref<InfoSource[]>([])
const tasks = ref<AnalysisTask[]>([])
const runs = ref<TaskRun[]>([])

onMounted(async () => {
  ;[sources.value, tasks.value, runs.value] = await Promise.all([
    listSourcesApi(),
    listTasksApi(),
    listRunsApi({ limit: 10 }),
  ])
})

function kindLabel(k: string) {
  return k === 'analysis' ? '分析' : k === 'sync' ? '同步' : k
}
function statusType(s: string) {
  if (s === 'succeeded') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'running') return 'warning'
  return 'info'
}
</script>

<style scoped>
.stat-num {
  font-size: 32px;
  font-weight: 700;
  color: #409eff;
  text-align: center;
}
.stat-label {
  text-align: center;
  color: #909399;
  margin-top: 6px;
}
.recent {
  margin-top: 16px;
}
</style>
