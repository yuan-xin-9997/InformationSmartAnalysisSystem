<template>
  <div>
    <div class="toolbar">
      <div class="button-row">
        <select v-model.number="taskId" style="width:auto" @change="onSwitch">
          <option v-for="t in tasks" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
        <button @click="load">刷新</button>
        <button @click="back">返回分析任务</button>
      </div>
      <div class="stats"><strong>{{ runs.length }}</strong><span>个运行批次</span></div>
    </div>

    <div v-if="!runs.length" class="empty"><b>暂无分析结果</b><span>触发分析任务后将在此展示。</span></div>
    <div v-else class="item-list">
      <article v-for="run in runs" :key="run.id" class="item-card" style="flex-direction:column;align-items:stretch">
        <div class="grow" style="cursor:pointer" @click="toggleRun(run.id)">
          <div class="item-title">
            <h3>运行 #{{ run.id }}</h3>
            <span :class="['pill', run.status]">{{ run.status }}</span>
            <span class="pill">{{ modeLabel(run.mode) }}</span>
          </div>
          <div class="meta">
            <span>{{ run.created_at }}</span>
            <span v-if="run.summary">{{ run.summary }}</span>
          </div>
        </div>
        <div v-if="expandedRun === run.id" style="margin-top:8px">
          <div v-if="!resultsByRun[run.id]" class="muted" style="font-size:12px">加载中...</div>
          <div v-else-if="!resultsByRun[run.id]?.length" class="muted" style="font-size:12px">该批次无结果</div>
          <div v-else>
            <details v-for="r in resultsByRun[run.id]" :key="r.id" style="margin-bottom:6px">
              <summary style="cursor:pointer">
                <span :class="['pill', r.result_type === 'aggregate' ? 'warning' : 'ok']">{{ r.result_type === 'aggregate' ? '汇总' : '逐条' }}</span>
                {{ r.source_name || '未知源' }} · {{ r.created_at }}
              </summary>
              <div class="markdown" style="margin-top:6px" v-html="renderMd(r.content)"></div>
            </details>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listTasksApi, listTaskResultsApi, listRunsApi, type AnalysisTaskDetail, type AnalysisResult, type TaskRun } from '@/api/tasks'
import { renderMarkdown } from '@/utils/markdown'

const route = useRoute()
const router = useRouter()
const tasks = ref<AnalysisTaskDetail[]>([])
const taskId = ref<number>(Number(route.params.id))
const runs = ref<TaskRun[]>([])
const expandedRun = ref<number | null>(null)
const resultsByRun = reactive<Record<number, AnalysisResult[] | undefined>>({})
const renderMd = renderMarkdown

onMounted(async () => {
  tasks.value = await listTasksApi()
  if (!tasks.value.find((t) => t.id === taskId.value) && tasks.value.length) {
    taskId.value = tasks.value[0].id
  }
  await loadRuns()
})

function onSwitch() {
  router.replace({ name: 'task-results', params: { id: taskId.value } })
  loadRuns()
}

function back() {
  router.push('/analysis-tasks')
}

async function load() {
  await loadRuns()
}

async function loadRuns() {
  runs.value = await listRunsApi({ kind: 'analysis', ref_id: taskId.value, limit: 200 })
  expandedRun.value = null
}

async function toggleRun(runId: number) {
  if (expandedRun.value === runId) {
    expandedRun.value = null
    return
  }
  expandedRun.value = runId
  if (!resultsByRun[runId]) {
    resultsByRun[runId] = await listTaskResultsApi(taskId.value, runId)
  }
}

function modeLabel(m?: string | null) {
  if (m === 'full') return '全量'
  if (m === 'custom') return '自定义'
  return '增量'
}
</script>
