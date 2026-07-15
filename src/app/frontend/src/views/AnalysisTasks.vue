<template>
  <div>
    <div class="toolbar">
      <div class="stats"><strong>{{ tasks.length }}</strong><span>个分析任务</span></div>
      <div class="button-row">
        <button @click="load">刷新</button>
        <button class="primary" @click="openCreate">＋ 新建分析任务</button>
      </div>
    </div>

    <div v-if="!tasks.length" class="empty">
      <b>还没有分析任务</b><span>新建任务并绑定信息源，即可触发智能分析。</span>
    </div>
    <div v-else class="item-list">
      <article v-for="t in tasks" :key="t.id" class="item-card">
        <div class="file-icon">析</div>
        <div class="grow">
          <div class="item-title">
            <h3>{{ t.name }}</h3>
            <span class="pill">{{ modeLabel(t.config?.mode as string | undefined) }}</span>
          </div>
          <p>{{ t.description || '无说明' }}</p>
          <div class="meta">
            <span>绑定 {{ t.sources.length }} 个源</span>
            <span>创建于 {{ t.created_at }}</span>
          </div>
        </div>
        <div class="actions">
          <button @click="openDetail(t)">源状态</button>
          <button class="accent" @click="onRun(t.id, 'incremental')">增量</button>
          <button @click="onRun(t.id, 'full')">全量</button>
          <button @click="goResults(t.id)">结果</button>
          <button @click="openEdit(t)">编辑</button>
          <button class="danger" @click="onDelete(t)">删除</button>
        </div>
      </article>
    </div>

    <div v-if="dialogVisible" class="modal" @click.self="dialogVisible = false">
      <form class="modal-card large" @submit.prevent="onSave">
        <div class="modal-head">
          <div><p class="eyebrow">ANALYSIS TASK</p><h2>{{ editing ? '编辑分析任务' : '新建分析任务' }}</h2></div>
          <button type="button" @click="dialogVisible = false">×</button>
        </div>
        <div class="form-grid">
          <label>名称<input v-model.trim="form.name" required /></label>
          <label>分析模式
            <select v-model="form.mode">
              <option value="per_item">逐条分析（per_item）</option>
              <option value="aggregate">汇总分析（aggregate）</option>
            </select>
          </label>
        </div>
        <label>说明<input v-model.trim="form.description" placeholder="可选" /></label>
        <fieldset>
          <legend>绑定信息源</legend>
          <label v-for="s in allSources" :key="s.id" class="check">
            <input type="checkbox" :value="s.id" v-model="form.source_ids" /> {{ s.name }}（{{ typeLabel(s.type) }}）
          </label>
          <p v-if="!allSources.length" class="muted">暂无信息源，请先在「信息源管理」添加。</p>
        </fieldset>
        <label>高级配置（JSON，可留空）
          <textarea v-model="configText" rows="4" placeholder='例如 {"max_items_per_source":50,"system_prompt":""}'></textarea>
        </label>
        <div class="modal-actions">
          <button type="button" @click="dialogVisible = false">取消</button>
          <button class="primary">保存</button>
        </div>
      </form>
    </div>

    <div v-if="detailVisible" class="modal" @click.self="detailVisible = false">
      <div class="modal-card large">
        <div class="modal-head">
          <div><p class="eyebrow">SOURCE STATUS</p><h2>信息源状态</h2></div>
          <button type="button" @click="detailVisible = false">×</button>
        </div>
        <div v-if="!detailSources.length" class="empty compact">未绑定信息源</div>
        <table v-else>
          <thead><tr><th>信息源</th><th>状态</th><th>条目数</th><th>水位线</th><th>最近分析</th></tr></thead>
          <tbody>
            <tr v-for="s in detailSources" :key="s.source_id">
              <td><strong>{{ s.source_name }}</strong></td>
              <td><span :class="['pill', s.source_status]">{{ s.source_status }}</span></td>
              <td>{{ s.item_count }}</td>
              <td>{{ s.last_analyzed_item_id ?? '-' }}</td>
              <td>{{ s.last_analyzed_at || '从未' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from '@/composables/toast'
import { listSourcesApi, type InfoSource } from '@/api/sources'
import {
  listTasksApi, createTaskApi, updateTaskApi, deleteTaskApi, runTaskApi, getTaskApi,
  type AnalysisTaskDetail, type TaskSourceOut,
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
function typeLabel(t: string) {
  return { website: '官方网站', local_folder: '本地文件夹', freshrss: 'FreshRSS' }[t] || t
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
function openEdit(t: AnalysisTaskDetail) {
  editing.value = t
  form.name = t.name
  form.description = t.description
  form.mode = (t.config?.mode as string) || 'per_item'
  form.source_ids = t.sources.map((s) => s.source_id)
  configText.value = JSON.stringify(t.config || {}, null, 2)
  dialogVisible.value = true
}

async function onSave() {
  let config: Record<string, unknown> = { mode: form.mode }
  if (configText.value.trim()) {
    try {
      config = JSON.parse(configText.value)
    } catch {
      showToast('高级配置不是合法的 JSON')
      return
    }
  }
  config.mode = form.mode
  try {
    if (editing.value) {
      await updateTaskApi(editing.value.id, {
        name: form.name, description: form.description, config, source_ids: form.source_ids,
      })
    } else {
      await createTaskApi({ name: form.name, description: form.description, config, source_ids: form.source_ids })
    }
    showToast('保存成功')
    dialogVisible.value = false
    await load()
  } catch {
    /* handled */
  }
}

async function onDelete(t: AnalysisTaskDetail) {
  if (!confirm(`确认删除分析任务「${t.name}」？`)) return
  await deleteTaskApi(t.id)
  showToast('已删除')
  await load()
}

async function onRun(id: number, mode: 'full' | 'incremental') {
  const { run_id } = await runTaskApi(id, mode)
  showToast(`已提交${mode === 'full' ? '全量' : '增量'}分析，运行 ID: ${run_id}`)
}

async function openDetail(t: AnalysisTaskDetail) {
  const detail = await getTaskApi(t.id)
  detailSources.value = detail.sources
  detailVisible.value = true
}

function goResults(taskId: number) {
  router.push({ path: '/analysis-result', query: { task_id: taskId } })
}
</script>
