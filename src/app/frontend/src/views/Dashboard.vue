<template>
  <div>
    <div class="item-list" style="grid-template-columns:1fr 1fr 1fr;gap:14px">
      <div class="item-card" style="cursor:default">
        <div class="file-icon">源</div>
        <div class="grow">
          <div class="item-title"><h3>信息源</h3></div>
          <div class="stats"><strong>{{ sources.length }}</strong><span>个</span></div>
        </div>
      </div>
      <div class="item-card" style="cursor:default">
        <div class="file-icon">析</div>
        <div class="grow">
          <div class="item-title"><h3>分析任务</h3></div>
          <div class="stats"><strong>{{ tasks.length }}</strong><span>个</span></div>
        </div>
      </div>
      <div class="item-card" style="cursor:default">
        <div class="file-icon">务</div>
        <div class="grow">
          <div class="item-title"><h3>最近运行</h3></div>
          <div class="stats"><strong>{{ runs.length }}</strong><span>条</span></div>
        </div>
      </div>
    </div>

    <div class="panel" style="margin-top:18px">
      <div class="panel-head"><h2>最近任务运行</h2><span>{{ runs.length }}</span></div>
      <div v-if="!runs.length" class="empty compact">暂无运行记录</div>
      <div v-for="run in runs" :key="run.id" class="log-row">
        <span :class="['status-dot', run.status]"></span>
        <div>
          <strong>{{ kindLabel(run.kind) }} · {{ run.ref_name || '-' }}</strong>
          <p>{{ run.summary || run.error || run.status }}</p>
        </div>
        <time>{{ run.started_at || run.created_at }}</time>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listSourcesApi, type InfoSource } from '@/api/sources'
import { listTasksApi, listRunsApi, type AnalysisTaskDetail, type TaskRun } from '@/api/tasks'

const sources = ref<InfoSource[]>([])
const tasks = ref<AnalysisTaskDetail[]>([])
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
</script>
