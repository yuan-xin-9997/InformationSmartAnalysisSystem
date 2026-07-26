<template>
  <div>
    <div class="toolbar">
      <div class="stats"><strong>{{ jobs.length }}</strong><span>个定时任务</span></div>
      <div class="button-row">
        <button @click="load">刷新</button>
        <button class="primary" @click="openCreate">＋ 新建定时任务</button>
      </div>
    </div>

    <div v-if="!jobs.length" class="empty"><b>还没有定时任务</b><span>为分析任务配置定时调度，自动触发分析。</span></div>
    <div v-else class="item-list">
      <article v-for="j in jobs" :key="j.id" class="item-card">
        <div class="file-icon">定</div>
        <div class="grow">
          <div class="item-title">
            <h3>{{ j.name }}</h3>
            <span :class="['pill', j.enabled ? 'ok' : '']">{{ j.enabled ? '启用' : '已停' }}</span>
            <span class="pill">{{ j.mode === 'full' ? '全量' : '增量' }}</span>
          </div>
          <div class="meta">
            <span>{{ taskName(j.task_id) }}</span>
            <span>{{ scheduleText(j) }}</span>
            <span>下次: {{ j.enabled ? (j.next_run_at || '-') : '已禁用' }}</span>
            <span>上次: {{ j.last_run_at || '-' }} ({{ j.last_run_status || '-' }})</span>
          </div>
        </div>
        <div class="actions">
          <button class="accent" @click="onRunNow(j.id)">立即执行</button>
          <button @click="onToggle(j)">{{ j.enabled ? '禁用' : '启用' }}</button>
          <button @click="openEdit(j)">编辑</button>
          <button class="danger" @click="onDelete(j)">删除</button>
        </div>
      </article>
    </div>

    <div v-if="dialogVisible" class="modal" @click.self="dialogVisible = false">
      <form class="modal-card large" @submit.prevent="onSave">
        <div class="modal-head">
          <div><p class="eyebrow">SCHEDULED JOB</p><h2>{{ editing ? '编辑定时任务' : '新建定时任务' }}</h2></div>
          <button type="button" @click="dialogVisible = false">×</button>
        </div>
        <div class="form-grid">
          <label>名称<input v-model.trim="form.name" required /></label>
          <label>所属分析任务
            <select v-model.number="form.task_id" required>
              <option v-for="t in tasks" :key="t.id" :value="t.id">{{ t.name }}</option>
            </select>
          </label>
          <label>执行模式
            <select v-model="form.mode">
              <option value="incremental">增量分析</option>
              <option value="full">全量分析</option>
            </select>
          </label>
          <label>触发类型
            <select v-model="form.trigger_type">
              <option value="cron">Cron 表达式</option>
              <option value="interval">固定间隔</option>
            </select>
          </label>
        </div>
        <label v-if="form.trigger_type === 'cron'">Cron 表达式
          <input v-model.trim="form.cron_expr" placeholder="如 0 9 * * * (每天9点)" required />
        </label>
        <div v-if="form.trigger_type === 'cron'" class="button-row" style="margin:6px 0">
          <button type="button" @click="form.cron_expr = '0 9 * * *'">每天9点</button>
          <button type="button" @click="form.cron_expr = '0 9 * * 1-5'">工作日9点</button>
          <button type="button" @click="form.cron_expr = '0 * * * *'">每小时</button>
          <button type="button" @click="form.cron_expr = '*/30 * * * *'">每30分钟</button>
        </div>
        <label v-if="form.trigger_type === 'interval'">间隔秒数
          <input v-model.number="form.interval_seconds" type="number" min="1" placeholder="如 1800 (30分钟)" required />
        </label>
        <label class="check"><input type="checkbox" v-model="form.enabled" /> 启用</label>
        <div class="modal-actions">
          <button type="button" @click="dialogVisible = false">取消</button>
          <button class="primary">保存</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { showToast } from '@/composables/toast'
import { listTasksApi, type AnalysisTaskDetail } from '@/api/tasks'
import {
  listScheduledJobsApi, createScheduledJobApi, updateScheduledJobApi,
  deleteScheduledJobApi, toggleScheduledJobApi, runScheduledJobNowApi,
  type ScheduledJob,
} from '@/api/scheduledJobs'

const jobs = ref<ScheduledJob[]>([])
const tasks = ref<AnalysisTaskDetail[]>([])
const dialogVisible = ref(false)
const editing = ref<ScheduledJob | null>(null)
const form = reactive({
  task_id: 0,
  name: '',
  mode: 'incremental' as 'full' | 'incremental',
  trigger_type: 'cron' as 'cron' | 'interval',
  cron_expr: '0 9 * * *',
  interval_seconds: 1800,
  enabled: true,
})

onMounted(async () => {
  tasks.value = await listTasksApi()
  if (tasks.value.length) form.task_id = tasks.value[0].id
  await load()
})

async function load() {
  jobs.value = await listScheduledJobsApi()
}

function taskName(tid: number) {
  return tasks.value.find((t) => t.id === tid)?.name || `#${tid}`
}

function scheduleText(j: ScheduledJob) {
  return j.trigger_type === 'cron' ? `cron: ${j.cron_expr}` : `每 ${Math.round((j.interval_seconds || 0) / 60)} 分钟`
}

function openCreate() {
  editing.value = null
  form.name = ''
  form.mode = 'incremental'
  form.trigger_type = 'cron'
  form.cron_expr = '0 9 * * *'
  form.interval_seconds = 1800
  form.enabled = true
  if (tasks.value.length) form.task_id = tasks.value[0].id
  dialogVisible.value = true
}

function openEdit(j: ScheduledJob) {
  editing.value = j
  form.task_id = j.task_id
  form.name = j.name
  form.mode = j.mode as 'full' | 'incremental'
  form.trigger_type = j.trigger_type as 'cron' | 'interval'
  form.cron_expr = j.cron_expr || '0 9 * * *'
  form.interval_seconds = j.interval_seconds || 1800
  form.enabled = j.enabled
  dialogVisible.value = true
}

async function onSave() {
  const data = {
    task_id: form.task_id,
    name: form.name,
    mode: form.mode,
    trigger_type: form.trigger_type,
    cron_expr: form.trigger_type === 'cron' ? form.cron_expr : undefined,
    interval_seconds: form.trigger_type === 'interval' ? form.interval_seconds : undefined,
    enabled: form.enabled,
  }
  try {
    if (editing.value) {
      await updateScheduledJobApi(editing.value.id, data)
    } else {
      await createScheduledJobApi(data)
    }
    showToast('保存成功')
    dialogVisible.value = false
    await load()
  } catch { /* handled */ }
}

async function onDelete(j: ScheduledJob) {
  if (!confirm(`确认删除定时任务「${j.name}」？`)) return
  await deleteScheduledJobApi(j.id)
  showToast('已删除')
  await load()
}

async function onToggle(j: ScheduledJob) {
  await toggleScheduledJobApi(j.id)
  showToast(j.enabled ? '已禁用' : '已启用')
  await load()
}

async function onRunNow(id: number) {
  const { run_id } = await runScheduledJobNowApi(id)
  showToast(`已提交执行，运行 ID: ${run_id}`)
}
</script>
