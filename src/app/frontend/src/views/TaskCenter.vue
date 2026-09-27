<template>
  <div>
    <div class="toolbar">
      <div class="button-row">
        <select v-model="kindFilter" @change="load" style="width:auto">
          <option :value="undefined">全部类型</option>
          <option value="analysis">分析</option>
          <option value="sync">更新数据</option>
        </select>
        <select v-model="statusFilter" @change="load" style="width:auto">
          <option :value="undefined">全部状态</option>
          <option value="pending">pending</option>
          <option value="running">running</option>
          <option value="succeeded">succeeded</option>
          <option value="failed">failed</option>
        </select>
        <button @click="load">刷新</button>
      </div>
      <div class="stats"><strong>{{ runs.length }}</strong><span>条运行</span></div>
    </div>

    <div class="two-columns">
      <div class="panel">
        <div class="panel-head"><h2>任务运行</h2><span>{{ runs.length }}</span></div>
        <div v-if="!runs.length" class="empty compact">暂无运行记录</div>
        <div
          v-for="run in runs"
          :key="run.id"
          class="log-row"
          style="cursor:pointer"
          @click="openLogs(run)"
        >
          <span :class="['status-dot', run.status]"></span>
          <div>
            <strong>#{{ run.id }} {{ kindLabel(run.kind) }} · {{ run.ref_name }}</strong>
            <p>{{ run.summary || run.error || run.status }}</p>
          </div>
          <time>{{ run.started_at || run.created_at }}</time>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head"><h2>运行日志</h2><span>{{ currentRun ? '#' + currentRun.id : '-' }}</span></div>
        <div v-if="!currentRun" class="empty compact">点击左侧运行查看日志</div>
        <div v-if="refreshDetail" class="panel" style="margin-bottom:12px;padding:12px">
          <strong>更新数据</strong>
          <p>开始：{{ formatTime(refreshDetail.started_at) }} · 结束：{{ formatTime(refreshDetail.finished_at) }}</p>
          <p v-for="source in refreshDetail.sources || []" :key="source.source_id">
            {{ source.source_name }} · {{ source.status === 'succeeded' ? '成功' : source.status === 'skipped' ? '跳过' : '失败' }}
            · 新增 {{ source.added_count }} · 更新 {{ source.updated_count }}
            <span v-if="source.reason || source.error"> · {{ source.reason || source.error }}</span>
          </p>
          <strong>分析</strong>
          <p>开始：{{ formatTime(refreshDetail.analysis_started_at) }} · 结束：{{ formatTime(refreshDetail.analysis_finished_at) }}</p>
        </div>
        <div v-for="log in logs" :key="log.id" class="log-row">
          <span :class="['status-dot', logLevelDot(log.level)]"></span>
          <div>
            <strong>[{{ log.level }}] {{ log.message }}</strong>
          </div>
          <time>{{ log.created_at }}</time>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listRunsApi, getRunApi, type TaskRun, type TaskRunDetail } from '@/api/tasks'
import { computed } from 'vue'

const runs = ref<TaskRun[]>([])
const kindFilter = ref<string | undefined>(undefined)
const statusFilter = ref<string | undefined>(undefined)
const currentRun = ref<TaskRun | null>(null)
const logs = ref<TaskRunDetail['logs']>([])
const refreshDetail = computed(() => detailRun.value?.refresh_detail)
const detailRun = ref<TaskRunDetail | null>(null)
function formatTime(value?: string) { return value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-' }

onMounted(load)

async function load() {
  runs.value = await listRunsApi({
    kind: kindFilter.value,
    status: statusFilter.value,
    limit: 200,
  })
}

function kindLabel(k: string) {
  return k === 'analysis' ? '分析' : k === 'sync' ? '更新数据' : k
}
function logLevelDot(level: string) {
  if (level === 'ERROR') return 'failed'
  if (level === 'WARNING') return 'running'
  return 'succeeded'
}

async function openLogs(run: TaskRun) {
  currentRun.value = run
  const detail = await getRunApi(run.id)
  detailRun.value = detail
  logs.value = detail.logs
}
</script>
