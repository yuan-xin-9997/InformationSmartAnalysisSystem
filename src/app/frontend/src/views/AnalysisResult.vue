<template>
  <div>
    <div class="toolbar">
      <div class="button-row">
        <select v-model="taskId" @change="load" style="width:auto">
          <option :value="undefined">全部任务</option>
          <option v-for="t in tasks" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
        <button @click="load">刷新</button>
      </div>
      <div class="stats"><strong>{{ results.length }}</strong><span>条结果</span></div>
    </div>

    <div v-if="!results.length" class="empty"><b>暂无分析结果</b><span>触发分析任务后将在此展示。</span></div>
    <div v-else class="item-list">
      <article v-for="r in results" :key="r.id" class="item-card" style="cursor:pointer" @click="openContent(r)">
        <div class="file-icon">{{ r.result_type === 'aggregate' ? '总' : '条' }}</div>
        <div class="grow">
          <div class="item-title">
            <h3>{{ r.source_name || '未知源' }}</h3>
            <span :class="['pill', r.result_type === 'aggregate' ? 'warning' : 'ok']">{{ r.result_type === 'aggregate' ? '汇总' : '逐条' }}</span>
          </div>
          <p>{{ stripMd(r.content).slice(0, 120) }}</p>
          <div class="meta"><span>{{ r.created_at }}</span></div>
        </div>
      </article>
    </div>

    <div v-if="contentVisible" class="modal" @click.self="contentVisible = false">
      <div class="modal-card large">
        <div class="modal-head">
          <div><p class="eyebrow">ANALYSIS</p><h2>分析内容</h2></div>
          <button type="button" @click="contentVisible = false">×</button>
        </div>
        <div class="markdown" v-html="renderMd(currentContent)"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  listTasksApi, listAllResultsApi, listTaskResultsApi,
  type AnalysisTask, type AnalysisResult,
} from '@/api/tasks'
import { renderMarkdown, stripMarkdown } from '@/utils/markdown'

const route = useRoute()
const tasks = ref<AnalysisTask[]>([])
const taskId = ref<number | undefined>(undefined)
const results = ref<AnalysisResult[]>([])
const contentVisible = ref(false)
const currentContent = ref('')

const renderMd = renderMarkdown
const stripMd = stripMarkdown

onMounted(async () => {
  tasks.value = await listTasksApi()
  const q = route.query.task_id
  if (q) taskId.value = Number(q)
  await load()
})

watch(() => route.query.task_id, (v) => {
  if (v) { taskId.value = Number(v); load() }
})

async function load() {
  if (taskId.value) {
    results.value = await listTaskResultsApi(taskId.value)
  } else {
    results.value = await listAllResultsApi({ limit: 100 })
  }
}

function openContent(r: AnalysisResult) {
  currentContent.value = r.content
  contentVisible.value = true
}
</script>
