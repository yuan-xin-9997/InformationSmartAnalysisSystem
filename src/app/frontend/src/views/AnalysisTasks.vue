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
      <b>还没有分析任务</b><span>新建任务并绑定信息源，即可在编辑里配置定时分析与推送。</span>
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
          <div class="meta">
            <span class="pill" :class="schedulePillClass(t.schedule)">定时：{{ scheduleSummary(t.schedule) }}</span>
            <span class="pill" :class="pushPillClass(t.push)">推送：{{ pushSummary(t.push) }}</span>
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
          <button v-if="t.schedule" @click="onRunSchedule(t.id)">立即执行</button>
          <button v-if="t.push" @click="onTriggerPush(t.id)">立即推送</button>
          <button @click="openPushHistory(t)">推送历史</button>
          <button @click="goResults(t.id)">结果</button>
          <button @click="openEdit(t)">编辑</button>
          <button class="danger" @click="onDelete(t)">删除</button>
        </div>
      </article>
    </div>

    <!-- 任务编辑弹窗（三 Tab：基本信息 / 定时分析 / 推送配置） -->
    <div v-if="dialogVisible" class="modal" @click.self="dialogVisible = false">
      <form class="modal-card large" @submit.prevent="onSave">
        <div class="modal-head">
          <div><p class="eyebrow">TASK ANALYSIS</p><h2>{{ editing ? '编辑任务分析' : '新建分析任务' }}</h2></div>
          <button type="button" @click="dialogVisible = false">×</button>
        </div>

        <div class="tabs">
          <button type="button" :class="{ active: activeTab === 'basic' }" @click="activeTab = 'basic'">
            基本信息
          </button>
          <button type="button" :class="{ active: activeTab === 'schedule' }" @click="activeTab = 'schedule'">
            定时分析 <span class="tab-badge" :class="scheduleFormEnabled() ? 'ok' : ''">{{ scheduleFormEnabled() ? '已配置' : '未配置' }}</span>
          </button>
          <button type="button" :class="{ active: activeTab === 'push' }" @click="activeTab = 'push'">
            推送配置 <span class="tab-badge" :class="pushFormEnabled() ? 'ok' : ''">{{ pushFormEnabled() ? '已配置' : '未配置' }}</span>
          </button>
        </div>

        <!-- 基本信息 -->
        <div v-show="activeTab === 'basic'">
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
          <label v-if="form.mode !== 'custom'">条目选择策略
            <select v-model="form.selectionStrategy">
              <option value="sequential">顺序分析（按入库顺序）</option>
              <option value="newest_unanalyzed">最新未分析优先</option>
            </select>
          </label>
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
        </div>

        <!-- 定时分析 -->
        <div v-show="activeTab === 'schedule'">
          <label class="check"><input type="checkbox" v-model="sched.enabled" /> 启用定时分析</label>
          <div class="form-grid">
            <label>执行模式
              <select v-model="sched.mode">
                <option value="incremental">增量分析</option>
                <option value="full">全量分析</option>
              </select>
            </label>
            <label>触发类型
              <select v-model="sched.trigger_type">
                <option value="cron">Cron 表达式</option>
                <option value="interval">固定间隔</option>
              </select>
            </label>
          </div>
          <label v-if="sched.trigger_type === 'cron'">Cron 表达式
            <input v-model.trim="sched.cron_expr" placeholder="如 0 9 * * * (每天9点)" />
          </label>
          <div v-if="sched.trigger_type === 'cron'" class="button-row" style="margin:6px 0">
            <button type="button" @click="sched.cron_expr = '0 9 * * *'">每天9点</button>
            <button type="button" @click="sched.cron_expr = '0 9 * * 1-5'">工作日9点</button>
            <button type="button" @click="sched.cron_expr = '0 * * * *'">每小时</button>
            <button type="button" @click="sched.cron_expr = '*/30 * * * *'">每30分钟</button>
          </div>
          <label v-if="sched.trigger_type === 'interval'">间隔秒数
            <input v-model.number="sched.interval_seconds" type="number" min="1" placeholder="如 1800 (30分钟)" />
          </label>
          <p class="muted" style="font-size:12px;margin-top:6px">每任务至多一条定时配置；保存后立即生效，无需重启。</p>
        </div>

        <!-- 推送配置 -->
        <div v-show="activeTab === 'push'">
          <label class="check"><input type="checkbox" v-model="push.enabled" /> 启用推送</label>
          <label>触发方式
            <select v-model="push.trigger_mode">
              <option value="on_run">分析任务完成后自动</option>
              <option value="scheduled">按计划定时</option>
              <option value="manual">仅手动</option>
            </select>
          </label>
          <label>事件类型（可多选）</label>
          <div class="button-row" style="margin:4px 0 12px">
            <label class="check"><input type="checkbox" value="per_item" v-model="push.event_types" /> 逐条分析</label>
            <label class="check"><input type="checkbox" value="aggregate" v-model="push.event_types" /> 汇总分析</label>
          </div>
          <label>收件人邮箱（多个用逗号分隔）
            <input v-model.trim="recipientsText" placeholder="a@example.com, b@example.com" />
          </label>
          <div v-if="push.trigger_mode === 'scheduled'" class="form-grid">
            <label>Cron 表达式
              <input v-model.trim="push.cron_expr" placeholder="如 0 9 * * * (每天9点)" />
            </label>
            <label>或 间隔秒数
              <input v-model.number="push.interval_seconds" type="number" min="1" placeholder="如 3600" />
            </label>
          </div>
          <p v-if="push.trigger_mode === 'scheduled'" class="muted" style="margin:4px 0">填写 cron 表达式或间隔秒数其中之一。</p>
          <label>每封邮件最大事件数
            <input v-model.number="push.max_events_per_email" type="number" min="1" />
          </label>
          <p class="muted" style="font-size:12px;margin-top:6px">每任务至多一条推送配置；SMTP 邮件通道见页面底部。</p>
        </div>

        <div class="modal-actions">
          <button type="button" @click="dialogVisible = false">取消</button>
          <button class="primary">保存</button>
        </div>
      </form>
    </div>

    <!-- 条目选择器（自定义模式） -->
    <div v-if="pickerVisible" class="modal" @click.self="pickerVisible = false">
      <div class="modal-card large">
        <div class="modal-head">
          <div><p class="eyebrow">PICK ITEMS</p><h2>选择要分析的条目（已选 {{ form.custom_item_ids.length }} 篇）</h2></div>
          <button type="button" @click="pickerVisible = false">×</button>
        </div>
        <div v-if="pickerSelected.length" class="picker-selected">
          <div class="picker-selected-head">
            <strong>已选 {{ pickerSelected.length }} 篇</strong>
            <button type="button" class="link" @click="clearSelected">全部取消</button>
          </div>
          <div class="picker-scroll">
            <table>
              <thead><tr><th>取消</th><th>标题</th><th>已分析</th><th>发布时间</th></tr></thead>
              <tbody>
                <tr v-for="it in pickerSelected" :key="it.id">
                  <td><input type="checkbox" :checked="true" @change="togglePick(it)" /></td>
                  <td>{{ it.title || '(无标题)' }}</td>
                  <td>{{ it.analyzed ? '是' : '否' }}</td>
                  <td>{{ it.published_at || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="toolbar" style="margin-bottom:12px">
          <div class="stats"><strong>{{ pickerTotal }}</strong><span>条可选</span></div>
          <div class="button-row">
            <input v-model="pickerKeyword" @input="onPickerKeywordInput" placeholder="按标题筛选" style="width:150px" />
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
          <thead><tr>
            <th>选择</th>
            <th class="sortable" @click="onSort('title')">标题 <span v-if="sortIcon('title')">{{ sortIcon('title') }}</span></th>
            <th class="sortable" @click="onSort('analyzed')">已分析 <span v-if="sortIcon('analyzed')">{{ sortIcon('analyzed') }}</span></th>
            <th class="sortable" @click="onSort('published_at')">发布时间 <span v-if="sortIcon('published_at')">{{ sortIcon('published_at') }}</span></th>
          </tr></thead>
          <tbody>
            <tr v-for="it in pickerItems" :key="it.id">
              <td><input type="checkbox" :checked="isPicked(it.id)" @change="togglePick(it)" /></td>
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

    <!-- 信息源状态 -->
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

    <!-- 按任务推送历史 -->
    <div v-if="historyVisible" class="modal" @click.self="historyVisible = false">
      <div class="modal-card large">
        <div class="modal-head">
          <div><p class="eyebrow">PUSH HISTORY</p><h2>推送历史 - {{ historyTask?.name }}</h2></div>
          <button type="button" @click="historyVisible = false">×</button>
        </div>
        <div v-if="!runs.length" class="empty compact">暂无推送记录</div>
        <div v-else class="item-list">
          <article v-for="run in runs" :key="run.id" class="item-card">
            <div class="file-icon">{{ run.status === 'succeeded' ? '✓' : run.status === 'failed' ? '✗' : '-' }}</div>
            <div class="grow">
              <div class="item-title">
                <h3>{{ statusLabel(run.status) }}</h3>
                <span class="pill">{{ triggerLabel(run.trigger_mode) }}</span>
                <span class="pill">{{ run.event_count }} 条</span>
              </div>
              <div class="meta">
                <span>收件: {{ run.recipients.join('; ') }}</span>
                <span>开始: {{ run.started_at || '-' }}</span>
                <span>结束: {{ run.finished_at || '-' }}</span>
                <span v-if="run.error" class="pill" style="color:#c00">错误: {{ run.error }}</span>
              </div>
            </div>
          </article>
        </div>
      </div>
    </div>

    <!-- 全局邮件通道（SMTP） -->
    <div class="toolbar" style="margin-top:24px">
      <div class="stats"><strong>SMTP</strong><span>邮件通道配置（页面优先于 app.json）</span></div>
      <div class="button-row">
        <button @click="smtpCollapsed = !smtpCollapsed">{{ smtpCollapsed ? '展开' : '收起' }}</button>
        <button @click="loadSmtp">重新加载</button>
        <button class="primary" @click="onSaveSmtp">保存配置</button>
        <button class="accent" @click="onTestSmtp">发送测试邮件</button>
      </div>
    </div>
    <div v-show="!smtpCollapsed" class="form-grid" style="margin-top:8px">
      <label>SMTP 主机<input v-model.trim="smtp.host" placeholder="smtp.example.com" /></label>
      <label>端口<input v-model.number="smtp.port" type="number" /></label>
      <label class="check"><input type="checkbox" v-model="smtp.use_tls" /> 启用 STARTTLS</label>
      <label class="check"><input type="checkbox" v-model="smtp.use_ssl" /> 启用 SSL</label>
      <label>用户名<input v-model.trim="smtp.username" /></label>
      <label>密码<input v-model.trim="smtp.password" type="password" placeholder="留空表示不修改" /></label>
      <label>发件人邮箱<input v-model.trim="smtp.from_email" placeholder="noreply@example.com" /></label>
      <label>发件人名称<input v-model.trim="smtp.from_name" /></label>
    </div>
    <p class="meta" style="margin-top:6px">
      当前生效来源：{{ smtpSource }}。密码为空保存时保留原密码；页面配置优先于 config/app.json 的 email 段。
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from '@/composables/toast'
import { listSourcesApi, queryItemsApi, type InfoSource, type InfoItemBrief } from '@/api/sources'
import {
  listTasksApi, createTaskApi, updateTaskApi, deleteTaskApi, runTaskApi, getTaskApi,
  runScheduleNowApi, triggerPushApi, listPushRunsApi,
  type AnalysisTaskDetail, type TaskSourceOut, type ScheduleConfig, type PushConfig,
} from '@/api/tasks'
import { getSmtpApi, putSmtpApi, testSmtpApi, type PushRun } from '@/api/push'

const router = useRouter()
const tasks = ref<AnalysisTaskDetail[]>([])
const allSources = ref<InfoSource[]>([])
const dialogVisible = ref(false)
const editing = ref<AnalysisTaskDetail | null>(null)
const activeTab = ref<'basic' | 'schedule' | 'push'>('basic')
const form = reactive({
  name: '',
  description: '',
  mode: 'per_item',
  selectionStrategy: 'sequential',
  source_ids: [] as number[],
  custom_item_ids: [] as number[],
})
const configText = ref('')
const detailVisible = ref(false)
const detailSources = ref<TaskSourceOut[]>([])

// 定时分析表单
const sched = reactive({
  enabled: false,
  mode: 'incremental' as 'full' | 'incremental',
  trigger_type: 'cron' as 'cron' | 'interval',
  cron_expr: '0 9 * * *',
  interval_seconds: 1800,
})
// 推送配置表单
const push = reactive({
  enabled: false,
  event_types: ['per_item'] as string[],
  recipients: [] as string[],
  trigger_mode: 'on_run' as 'on_run' | 'scheduled' | 'manual',
  cron_expr: '0 9 * * *',
  interval_seconds: 3600,
  max_events_per_email: 50,
})
const recipientsText = ref('')

// 推送历史
const historyVisible = ref(false)
const historyTask = ref<AnalysisTaskDetail | null>(null)
const runs = ref<PushRun[]>([])

// SMTP
const smtpCollapsed = ref(true)
const smtp = reactive({
  host: '', port: 25, use_tls: false, use_ssl: false,
  username: '', password: '', from_email: '', from_name: '信息智能分析系统',
})
const smtpSource = ref('加载中…')

// 条目选择器（自定义模式）
const pickerVisible = ref(false)
const pickerItems = ref<InfoItemBrief[]>([])
const pickerPage = ref(1)
const pickerPageSize = ref(50)
const pickerFilter = ref<'' | 'analyzed' | 'unanalyzed'>('')
const pickerTotal = ref(0)
const pickerTotalPages = computed(() => Math.max(1, Math.ceil(pickerTotal.value / pickerPageSize.value)))
const pickerSelected = ref<InfoItemBrief[]>([])
const pickerSortBy = ref<string | null>(null)
const pickerSortOrder = ref<'asc' | 'desc'>('desc')
const pickerKeyword = ref('')
let pickerKeywordTimer: ReturnType<typeof setTimeout> | null = null
let pickerReqId = 0

onMounted(async () => {
  await load()
  allSources.value = await listSourcesApi()
  await loadSmtp()
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
function triggerLabel(m: string) {
  return m === 'on_run' ? '完成后自动' : m === 'scheduled' ? '定时' : '手动'
}
function statusLabel(s: string) {
  return s === 'succeeded' ? '成功' : s === 'failed' ? '失败' : '无新事件'
}

// ---- 状态摘要 ----
function scheduleText(s: ScheduleConfig | null): string {
  if (!s) return '未配置'
  if (!s.enabled) return '已停用'
  if (s.trigger_type === 'cron') return s.cron_expr ? `cron ${s.cron_expr}` : 'cron'
  const secs = s.interval_seconds || 0
  return secs && secs < 60 ? `每 ${secs} 秒` : `每 ${Math.round(secs / 60)} 分钟`
}
function scheduleSummary(s: ScheduleConfig | null) {
  return scheduleText(s)
}
function schedulePillClass(s: ScheduleConfig | null) {
  if (!s) return ''
  return s.enabled ? 'ok' : ''
}
function pushSummary(p: PushConfig | null): string {
  if (!p) return '未配置'
  if (!p.enabled) return '已停用'
  return `${p.recipients.length} 收件人·${triggerLabel(p.trigger_mode)}`
}
function pushPillClass(p: PushConfig | null) {
  if (!p) return ''
  return p.enabled ? 'ok' : ''
}
function scheduleFormEnabled() {
  return sched.enabled
}
function pushFormEnabled() {
  return push.enabled
}

// ---- 编辑弹窗 ----
function openCreate() {
  editing.value = null
  activeTab.value = 'basic'
  form.name = ''
  form.description = ''
  form.mode = 'per_item'
  form.selectionStrategy = 'sequential'
  form.source_ids = []
  form.custom_item_ids = []
  configText.value = ''
  sched.enabled = false
  sched.mode = 'incremental'
  sched.trigger_type = 'cron'
  sched.cron_expr = '0 9 * * *'
  sched.interval_seconds = 1800
  push.enabled = false
  push.event_types = ['per_item']
  push.recipients = []
  recipientsText.value = ''
  push.trigger_mode = 'on_run'
  push.cron_expr = '0 9 * * *'
  push.interval_seconds = 3600
  push.max_events_per_email = 50
  dialogVisible.value = true
}

function openEdit(t: AnalysisTaskDetail) {
  editing.value = t
  activeTab.value = 'basic'
  form.name = t.name
  form.description = t.description
  form.mode = (t.config?.mode as string) || 'per_item'
  form.selectionStrategy = (t.config?.selection_strategy as string) === 'newest_unanalyzed' ? 'newest_unanalyzed' : 'sequential'
  form.source_ids = t.sources.map((s) => s.source_id)
  form.custom_item_ids = [...((t.config?.custom_item_ids as number[] | undefined) || [])]
  configText.value = JSON.stringify(t.config || {}, null, 2)
  // 定时分析
  const s = t.schedule
  sched.enabled = !!s?.enabled
  sched.mode = (s?.mode as 'full' | 'incremental') || 'incremental'
  sched.trigger_type = (s?.trigger_type as 'cron' | 'interval') || 'cron'
  sched.cron_expr = s?.cron_expr || '0 9 * * *'
  sched.interval_seconds = s?.interval_seconds || 1800
  // 推送配置
  const p = t.push
  push.enabled = !!p?.enabled
  push.event_types = [...(p?.event_types || ['per_item'])]
  push.recipients = [...(p?.recipients || [])]
  recipientsText.value = (p?.recipients || []).join(', ')
  push.trigger_mode = (p?.trigger_mode as 'on_run' | 'scheduled' | 'manual') || 'on_run'
  push.cron_expr = p?.cron_expr || '0 9 * * *'
  push.interval_seconds = p?.interval_seconds || 3600
  push.max_events_per_email = p?.max_events_per_email || 50
  dialogVisible.value = true
}

function buildSchedule(): ScheduleConfig | null {
  if (!sched.enabled) return null
  return {
    enabled: true,
    mode: sched.mode,
    trigger_type: sched.trigger_type,
    cron_expr: sched.trigger_type === 'cron' ? sched.cron_expr : null,
    interval_seconds: sched.trigger_type === 'interval' ? sched.interval_seconds : null,
  }
}
function buildPush(): PushConfig | null {
  if (!push.enabled) return null
  const recips = recipientsText.value.split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean)
  return {
    enabled: true,
    event_types: push.event_types,
    recipients: recips,
    trigger_mode: push.trigger_mode,
    cron_expr: push.trigger_mode === 'scheduled' ? push.cron_expr || null : null,
    interval_seconds: push.trigger_mode === 'scheduled' ? push.interval_seconds || null : null,
    max_events_per_email: push.max_events_per_email,
  }
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
  config.selection_strategy = form.selectionStrategy
  if (form.mode === 'custom') {
    config.custom_item_ids = form.custom_item_ids
    if (!form.custom_item_ids.length) {
      showToast('自定义模式请先选择要分析的条目')
      return
    }
  } else {
    delete config.custom_item_ids
  }
  const schedule = buildSchedule()
  const pushCfg = buildPush()
  if (pushCfg && !pushCfg.recipients.length) {
    showToast('启用推送时请填写至少一个收件人邮箱')
    return
  }
  if (pushCfg && !pushCfg.event_types.length) {
    showToast('启用推送时请选择至少一种事件类型')
    return
  }
  try {
    if (editing.value) {
      await updateTaskApi(editing.value.id, {
        name: form.name, description: form.description, config, source_ids: form.source_ids,
        schedule, push: pushCfg,
      })
    } else {
      await createTaskApi({
        name: form.name, description: form.description, config, source_ids: form.source_ids,
        schedule, push: pushCfg,
      })
    }
    showToast('保存成功')
    dialogVisible.value = false
    await load()
  } catch {
    /* handled */
  }
}

async function onDelete(t: AnalysisTaskDetail) {
  if (!confirm(`确认删除分析任务「${t.name}」？其定时与推送配置将一并删除。`)) return
  await deleteTaskApi(t.id)
  showToast('已删除')
  await load()
}

async function onRun(id: number, mode: 'full' | 'incremental' | 'custom') {
  const { run_id } = await runTaskApi(id, mode)
  const label = mode === 'full' ? '全量' : mode === 'custom' ? '自定义' : '增量'
  showToast(`已提交${label}分析，运行 ID: ${run_id}`)
}
async function onRunSchedule(id: number) {
  const { run_id } = await runScheduleNowApi(id)
  showToast(`已提交执行，运行 ID: ${run_id}`)
}
async function onTriggerPush(id: number) {
  await triggerPushApi(id)
  showToast('已提交推送，请稍后在推送历史中查看结果')
}

async function openDetail(t: AnalysisTaskDetail) {
  const detail = await getTaskApi(t.id)
  detailSources.value = detail.sources
  detailVisible.value = true
}

async function openPushHistory(t: AnalysisTaskDetail) {
  historyTask.value = t
  historyVisible.value = true
  runs.value = []
  runs.value = await listPushRunsApi(t.id)
}

function goResults(taskId: number) {
  router.push({ name: 'task-results', params: { id: taskId } })
}

// ---- SMTP ----
async function loadSmtp() {
  const cfg = await getSmtpApi()
  smtp.host = cfg.host
  smtp.port = cfg.port
  smtp.use_tls = cfg.use_tls
  smtp.use_ssl = cfg.use_ssl
  smtp.username = cfg.username
  smtp.password = ''
  smtp.from_email = cfg.from_email
  smtp.from_name = cfg.from_name
  smtpSource.value = cfg.host ? '页面配置' : 'app.json（或未配置）'
}
async function onSaveSmtp() {
  await putSmtpApi({
    host: smtp.host, port: smtp.port, use_tls: smtp.use_tls, use_ssl: smtp.use_ssl,
    username: smtp.username, password: smtp.password,
    from_email: smtp.from_email, from_name: smtp.from_name,
  })
  showToast('SMTP 配置已保存')
  await loadSmtp()
}
async function onTestSmtp() {
  const to = prompt('请输入测试收件人邮箱：')
  if (!to) return
  const res = await testSmtpApi(to.trim())
  showToast(res.ok ? '测试邮件发送成功' : `发送失败：${res.error}`)
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
  const myId = ++pickerReqId
  const a = pickerAnalyzed()
  const offset = (pickerPage.value - 1) * pickerPageSize.value
  const r = await queryItemsApi(form.source_ids, pickerPageSize.value, offset, a, {
    exclude_ids: form.custom_item_ids,
    sort_by: pickerSortBy.value || undefined,
    order: pickerSortBy.value ? pickerSortOrder.value : undefined,
    keyword: pickerKeyword.value.trim() || undefined,
  })
  if (myId !== pickerReqId) return
  pickerItems.value = r.items
  pickerTotal.value = r.total
}
async function loadSelected() {
  if (!form.custom_item_ids.length) {
    pickerSelected.value = []
    return
  }
  const r = await queryItemsApi(form.source_ids, form.custom_item_ids.length, 0, undefined, {
    ids: form.custom_item_ids,
  })
  pickerSelected.value = r.items
}
async function openPicker() {
  if (!form.source_ids.length) {
    showToast('请先在「绑定信息源」勾选来源')
    return
  }
  pickerPage.value = 1
  pickerFilter.value = ''
  pickerPageSize.value = 50
  pickerSortBy.value = null
  pickerSortOrder.value = 'desc'
  pickerKeyword.value = ''
  await loadSelected()
  await loadPicker()
  pickerVisible.value = true
}
function onPickerFilterChange() { pickerPage.value = 1; loadPicker() }
function onPickerPageSizeChange() { pickerPage.value = 1; loadPicker() }
function onPickerKeywordInput() {
  if (pickerKeywordTimer) clearTimeout(pickerKeywordTimer)
  pickerKeywordTimer = setTimeout(() => { pickerPage.value = 1; loadPicker() }, 300)
}
function onSort(col: string) {
  if (pickerSortBy.value !== col) { pickerSortBy.value = col; pickerSortOrder.value = 'asc' }
  else { pickerSortOrder.value = pickerSortOrder.value === 'asc' ? 'desc' : 'asc' }
  pickerPage.value = 1
  loadPicker()
}
function sortIcon(col: string): string {
  if (pickerSortBy.value !== col) return ''
  return pickerSortOrder.value === 'asc' ? '▲' : '▼'
}
function pickerPrev() { if (pickerPage.value > 1) { pickerPage.value--; loadPicker() } }
function pickerNext() { if (pickerPage.value < pickerTotalPages.value) { pickerPage.value++; loadPicker() } }
function isPicked(id: number) { return form.custom_item_ids.includes(id) }
function togglePick(it: InfoItemBrief) {
  if (isPicked(it.id)) {
    form.custom_item_ids = form.custom_item_ids.filter((x) => x !== it.id)
    pickerSelected.value = pickerSelected.value.filter((s) => s.id !== it.id)
  } else {
    form.custom_item_ids = [...form.custom_item_ids, it.id]
    pickerSelected.value = [...pickerSelected.value, it]
  }
  loadPicker()
}
function clearSelected() {
  form.custom_item_ids = []
  pickerSelected.value = []
  loadPicker()
}
</script>

<style scoped>
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border, #e5e7eb); margin-bottom: 12px; }
.tabs button { background: none; border: none; padding: 8px 14px; cursor: pointer; border-bottom: 2px solid transparent; font-size: 14px; color: var(--muted, #6b7280); }
.tabs button.active { color: var(--primary, #2563eb); border-bottom-color: var(--primary, #2563eb); font-weight: 600; }
.tab-badge { font-size: 11px; padding: 1px 6px; border-radius: 8px; background: #e5e7eb; color: #6b7280; margin-left: 4px; }
.tab-badge.ok { background: #dcfce7; color: #16a34a; }
</style>
