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
            <span v-if="(t.config?.mode as string) === 'custom'">已选 {{ (t.config?.custom_item_ids as number[] | undefined)?.length || 0 }} 篇</span>
            <span>创建于 {{ t.created_at }}</span>
          </div>
        </div>
        <div class="actions">
          <button @click="openDetail(t)">源状态</button>
          <template v-if="(t.config?.mode as string) === 'custom'">
            <button class="accent" @click="onRun(t.id, 'custom')">运行分析</button>
          </template>
          <template v-else>
            <button class="accent" @click="onRun(t.id, 'incremental')">增量</button>
            <button @click="onRun(t.id, 'full')">全量</button>
          </template>
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
              <option value="custom">自定义（指定条目）</option>
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
        <div v-if="form.mode === 'custom'">
          <label>自定义条目
            <button type="button" @click="openPicker">选择条目（已选 {{ form.custom_item_ids.length }} 篇）</button>
          </label>
          <p v-if="!form.source_ids.length" class="muted" style="font-size:12px;margin-top:6px">请先在「绑定信息源」勾选来源，再选择条目。</p>
        </div>
        <label>高级配置（JSON，可留空）
          <textarea v-model="configText" rows="4" placeholder='例如 {"max_items_per_source":50,"system_prompt":""}'></textarea>
        </label>
        <div class="modal-actions">
          <button type="button" @click="dialogVisible = false">取消</button>
          <button class="primary">保存</button>
        </div>
      </form>
    </div>

    <div v-if="pickerVisible" class="modal" @click.self="pickerVisible = false">
      <div class="modal-card large">
        <div class="modal-head">
          <div><p class="eyebrow">PICK ITEMS</p><h2>选择要分析的条目（已选 {{ form.custom_item_ids.length }} 篇）</h2></div>
          <button type="button" @click="pickerVisible = false">×</button>
        </div>
        <div class="toolbar" style="margin-bottom:12px">
          <div class="stats"><strong>{{ pickerTotal }}</strong><span>条可选</span></div>
          <div class="button-row">
            <select v-model="pickerFilter" style="width:auto" @change="onPickerFilterChange">
              <option value="">全部</option>
              <option value="analyzed">已分析</option>
              <option value="unanalyzed">未分析</option>
            </select>
            <select v-model.number="pickerPageSize" style="width:auto" @change="onPickerPageSizeChange">
              <option :value="50">50/页</option>
              <option :value="100">100/页</option>
              <option :value="200">200/页</option>
            </select>
          </div>
        </div>
        <div v-if="!pickerItems.length" class="empty compact">无符合条件的条目</div>
        <table v-else>
          <thead><tr><th>选择</th><th>标题</th><th>已分析</th><th>发布时间</th></tr></thead>
          <tbody>
            <tr v-for="it in pickerItems" :key="it.id">
              <td><input type="checkbox" :checked="isPicked(it.id)" @change="togglePick(it.id)" /></td>
              <td>{{ it.title || '(无标题)' }}</td>
              <td>{{ it.analyzed ? '是' : '否' }}</td>
              <td>{{ it.published_at || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <div class="toolbar" style="margin-top:12px">
          <span class="muted" style="font-size:12px">第 {{ pickerPage }} / {{ pickerTotalPages }} 页</span>
          <div class="button-row">
            <button :disabled="pickerPage <= 1" @click="pickerPrev">上一页</button>
            <button :disabled="pickerPage >= pickerTotalPages" @click="pickerNext">下一页</button>
            <button class="primary" @click="pickerVisible = false">完成</button>
          </div>
        </div>
      </div>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from '@/composables/toast'
import { listSourcesApi, queryItemsApi, type InfoSource, type InfoItemBrief } from '@/api/sources'
import {
  listTasksApi, createTaskApi, updateTaskApi, deleteTaskApi, runTaskApi, getTaskApi,
  type AnalysisTaskDetail, type TaskSourceOut,
} from '@/api/tasks'

const router = useRouter()
const tasks = ref<AnalysisTaskDetail[]>([])
const allSources = ref<InfoSource[]>([])
const dialogVisible = ref(false)
const editing = ref<AnalysisTaskDetail | null>(null)
const form = reactive({
  name: '',
  description: '',
  mode: 'per_item',
  source_ids: [] as number[],
  custom_item_ids: [] as number[],
})
const configText = ref('')
const detailVisible = ref(false)
const detailSources = ref<TaskSourceOut[]>([])

// 条目选择器（自定义模式）
const pickerVisible = ref(false)
const pickerItems = ref<InfoItemBrief[]>([])
const pickerPage = ref(1)
const pickerPageSize = ref(50)
const pickerFilter = ref<'' | 'analyzed' | 'unanalyzed'>('')
const pickerTotal = ref(0)
const pickerTotalPages = computed(() => Math.max(1, Math.ceil(pickerTotal.value / pickerPageSize.value)))

onMounted(async () => {
  await load()
  allSources.value = await listSourcesApi()
})

async function load() {
  tasks.value = await listTasksApi()
}

function modeLabel(m?: string) {
  if (m === 'aggregate') return '汇总分析'
  if (m === 'custom') return '自定义'
  return '逐条分析'
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
  form.custom_item_ids = []
  configText.value = ''
  dialogVisible.value = true
}
function openEdit(t: AnalysisTaskDetail) {
  editing.value = t
  form.name = t.name
  form.description = t.description
  form.mode = (t.config?.mode as string) || 'per_item'
  form.source_ids = t.sources.map((s) => s.source_id)
  form.custom_item_ids = [...((t.config?.custom_item_ids as number[] | undefined) || [])]
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
  if (form.mode === 'custom') {
    config.custom_item_ids = form.custom_item_ids
    if (!form.custom_item_ids.length) {
      showToast('自定义模式请先选择要分析的条目')
      return
    }
  } else {
    delete config.custom_item_ids
  }
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

async function onRun(id: number, mode: 'full' | 'incremental' | 'custom') {
  const { run_id } = await runTaskApi(id, mode)
  const label = mode === 'full' ? '全量' : mode === 'custom' ? '自定义' : '增量'
  showToast(`已提交${label}分析，运行 ID: ${run_id}`)
}

async function openDetail(t: AnalysisTaskDetail) {
  const detail = await getTaskApi(t.id)
  detailSources.value = detail.sources
  detailVisible.value = true
}

function goResults(taskId: number) {
  router.push({ path: '/analysis-result', query: { task_id: taskId } })
}

// ---- 条目选择器 ----
function pickerAnalyzed(): boolean | undefined {
  return pickerFilter.value === 'analyzed' ? true : pickerFilter.value === 'unanalyzed' ? false : undefined
}
async function loadPicker() {
  if (!form.source_ids.length) {
    pickerItems.value = []
    pickerTotal.value = 0
    return
  }
  const a = pickerAnalyzed()
  const offset = (pickerPage.value - 1) * pickerPageSize.value
  const r = await queryItemsApi(form.source_ids, pickerPageSize.value, offset, a)
  pickerItems.value = r.items
  pickerTotal.value = r.total
}
async function openPicker() {
  if (!form.source_ids.length) {
    showToast('请先在「绑定信息源」勾选来源')
    return
  }
  pickerPage.value = 1
  pickerFilter.value = ''
  pickerPageSize.value = 50
  await loadPicker()
  pickerVisible.value = true
}
function onPickerFilterChange() {
  pickerPage.value = 1
  loadPicker()
}
function onPickerPageSizeChange() {
  pickerPage.value = 1
  loadPicker()
}
function pickerPrev() {
  if (pickerPage.value > 1) {
    pickerPage.value--
    loadPicker()
  }
}
function pickerNext() {
  if (pickerPage.value < pickerTotalPages.value) {
    pickerPage.value++
    loadPicker()
  }
}
function isPicked(id: number) {
  return form.custom_item_ids.includes(id)
}
function togglePick(id: number) {
  if (isPicked(id)) {
    form.custom_item_ids = form.custom_item_ids.filter((x) => x !== id)
  } else {
    form.custom_item_ids = [...form.custom_item_ids, id]
  }
}
</script>
