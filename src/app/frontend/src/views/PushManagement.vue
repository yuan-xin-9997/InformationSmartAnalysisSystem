<template>
  <div>
    <div class="toolbar">
      <div class="stats"><strong>{{ rules.length }}</strong><span>个推送规则</span></div>
      <div class="button-row">
        <button @click="loadRules">刷新</button>
        <button class="primary" @click="openCreate">＋ 新建推送规则</button>
      </div>
    </div>

    <div v-if="!rules.length" class="empty">
      <b>还没有推送规则</b>
      <span>选定任务与事件类型，把增量分析结果推送到邮箱。</span>
    </div>
    <div v-else class="item-list">
      <article v-for="r in rules" :key="r.id" class="item-card">
        <div class="file-icon">推</div>
        <div class="grow">
          <div class="item-title">
            <h3>{{ r.name }}</h3>
            <span :class="['pill', r.enabled ? 'ok' : '']">{{ r.enabled ? '启用' : '已停' }}</span>
            <span class="pill">{{ triggerLabel(r.trigger_mode) }}</span>
          </div>
          <div class="meta">
            <span>任务: {{ taskNames(r.task_ids) }}</span>
            <span>类型: {{ typeLabels(r.event_types) }}</span>
            <span>收件: {{ r.recipients.join('; ') || '-' }}</span>
            <span v-if="r.trigger_mode === 'scheduled'">{{ scheduleText(r) }}</span>
            <span>水位线: {{ r.last_pushed_result_id ?? '尚未推送' }}</span>
          </div>
        </div>
        <div class="actions">
          <button class="accent" @click="onTrigger(r)">立即推送</button>
          <button @click="onToggle(r)">{{ r.enabled ? '禁用' : '启用' }}</button>
          <button @click="openHistory(r)">历史</button>
          <button @click="openEdit(r)">编辑</button>
          <button class="danger" @click="onDelete(r)">删除</button>
        </div>
      </article>
    </div>

    <!-- 规则编辑弹窗 -->
    <div v-if="dialogVisible" class="modal" @click.self="dialogVisible = false">
      <form class="modal-card large" @submit.prevent="onSave">
        <div class="modal-head">
          <div><p class="eyebrow">PUSH RULE</p><h2>{{ editing ? '编辑推送规则' : '新建推送规则' }}</h2></div>
          <button type="button" @click="dialogVisible = false">×</button>
        </div>
        <div class="form-grid">
          <label>规则名称<input v-model.trim="form.name" required /></label>
          <label>触发方式
            <select v-model="form.trigger_mode">
              <option value="on_run">分析任务完成后自动</option>
              <option value="scheduled">按计划定时</option>
              <option value="manual">仅手动</option>
            </select>
          </label>
          <label>每封邮件最大事件数
            <input v-model.number="form.max_events_per_email" type="number" min="1" />
          </label>
          <label class="check"><input type="checkbox" v-model="form.enabled" /> 启用</label>
        </div>

        <label>分析任务（可多选）</label>
        <div class="button-row" style="margin:4px 0 8px; flex-wrap:wrap">
          <label v-for="t in tasks" :key="t.id" class="check">
            <input type="checkbox" :value="t.id" v-model="form.task_ids" /> {{ t.name }}
          </label>
          <span v-if="!tasks.length" class="meta">暂无分析任务</span>
        </div>

        <label>事件类型（可多选）</label>
        <div class="button-row" style="margin:4px 0 12px">
          <label class="check"><input type="checkbox" value="per_item" v-model="form.event_types" /> 逐条分析</label>
          <label class="check"><input type="checkbox" value="aggregate" v-model="form.event_types" /> 汇总分析</label>
        </div>

        <label>收件人邮箱（多个用逗号分隔）
          <input v-model.trim="recipientsText" placeholder="a@example.com, b@example.com" required />
        </label>

        <div v-if="form.trigger_mode === 'scheduled'" class="form-grid">
          <label>Cron 表达式
            <input v-model.trim="form.cron_expr" placeholder="如 0 9 * * * (每天9点)" />
          </label>
          <label>或 间隔秒数
            <input v-model.number="form.interval_seconds" type="number" min="1" placeholder="如 3600" />
          </label>
        </div>
        <p v-if="form.trigger_mode === 'scheduled'" class="meta" style="margin:4px 0">
          填写 cron 表达式或间隔秒数其中之一。
        </p>

        <div class="modal-actions">
          <button type="button" @click="dialogVisible = false">取消</button>
          <button class="primary">保存</button>
        </div>
      </form>
    </div>

    <!-- 推送历史弹窗 -->
    <div v-if="historyVisible" class="modal" @click.self="historyVisible = false">
      <div class="modal-card large">
        <div class="modal-head">
          <div><p class="eyebrow">PUSH HISTORY</p><h2>推送历史 - {{ historyRule?.name }}</h2></div>
          <button type="button" @click="historyVisible = false">×</button>
        </div>
        <div v-if="!runs.length" class="empty"><span>暂无推送记录</span></div>
        <div v-else class="item-list">
          <article v-for="run in runs" :key="run.id" class="item-card">
            <div class="file-icon">{{ run.status === 'succeeded' ? '✓' : run.status === 'failed' ? '✗' : '—' }}</div>
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

    <!-- SMTP 配置 -->
    <div class="toolbar" style="margin-top:24px">
      <div class="stats"><strong>SMTP</strong><span>邮件发送配置（页面优先于 app.json）</span></div>
      <div class="button-row">
        <button @click="loadSmtp">重新加载</button>
        <button class="primary" @click="onSaveSmtp">保存配置</button>
        <button class="accent" @click="onTestSmtp">发送测试邮件</button>
      </div>
    </div>
    <div class="form-grid" style="margin-top:8px">
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
import { showToast } from '@/composables/toast'
import { listTasksApi, type AnalysisTaskDetail } from '@/api/tasks'
import {
  getSmtpApi, putSmtpApi, testSmtpApi,
  listRulesApi, createRuleApi, updateRuleApi, deleteRuleApi, triggerRuleApi, listRunsApi,
  type PushRule, type PushRun, type TriggerMode, type RuleForm,
} from '@/api/push'

const rules = ref<PushRule[]>([])
const tasks = ref<AnalysisTaskDetail[]>([])
const dialogVisible = ref(false)
const editing = ref<PushRule | null>(null)
const historyVisible = ref(false)
const historyRule = ref<PushRule | null>(null)
const runs = ref<PushRun[]>([])

const form = reactive<RuleForm>({
  name: '',
  task_ids: [],
  event_types: ['per_item'],
  recipients: [],
  trigger_mode: 'on_run',
  cron_expr: '0 9 * * *',
  interval_seconds: 3600,
  enabled: true,
  max_events_per_email: 50,
})
const recipientsText = ref('')

const smtp = reactive({
  host: '',
  port: 25,
  use_tls: false,
  use_ssl: false,
  username: '',
  password: '',
  from_email: '',
  from_name: '信息智能分析系统',
})
const smtpSource = ref('加载中…')

onMounted(async () => {
  tasks.value = await listTasksApi()
  await Promise.all([loadRules(), loadSmtp()])
})

async function loadRules() {
  rules.value = await listRulesApi()
}

async function loadSmtp() {
  const cfg = await getSmtpApi()
  smtp.host = cfg.host
  smtp.port = cfg.port
  smtp.use_tls = cfg.use_tls
  smtp.use_ssl = cfg.use_ssl
  smtp.username = cfg.username
  smtp.password = '' // 不回填明文，留空表示保留
  smtp.from_email = cfg.from_email
  smtp.from_name = cfg.from_name
  smtpSource.value = cfg.host ? '页面配置' : 'app.json（或未配置）'
}

function triggerLabel(m: string) {
  return m === 'on_run' ? '完成后自动' : m === 'scheduled' ? '定时' : '手动'
}
function statusLabel(s: string) {
  return s === 'succeeded' ? '成功' : s === 'failed' ? '失败' : '无新事件'
}
function typeLabels(types: string[]) {
  return types.map((t) => (t === 'per_item' ? '逐条' : t === 'aggregate' ? '汇总' : t)).join('/') || '-'
}
function taskNames(ids: number[]) {
  if (!ids.length) return '-'
  return ids.map((id) => tasks.value.find((t) => t.id === id)?.name || `#${id}`).join(', ')
}
function scheduleText(r: PushRule) {
  if (r.cron_expr) return `cron: ${r.cron_expr}`
  const secs = r.interval_seconds || 0
  return secs && secs < 60 ? `每 ${secs} 秒` : `每 ${Math.round(secs / 60)} 分钟`
}

function openCreate() {
  editing.value = null
  form.name = ''
  form.task_ids = []
  form.event_types = ['per_item']
  form.recipients = []
  recipientsText.value = ''
  form.trigger_mode = 'on_run'
  form.cron_expr = '0 9 * * *'
  form.interval_seconds = 3600
  form.enabled = true
  form.max_events_per_email = 50
  dialogVisible.value = true
}

function openEdit(r: PushRule) {
  editing.value = r
  form.name = r.name
  form.task_ids = [...r.task_ids]
  form.event_types = [...r.event_types]
  form.recipients = [...r.recipients]
  recipientsText.value = r.recipients.join(', ')
  form.trigger_mode = r.trigger_mode
  form.cron_expr = r.cron_expr ?? '0 9 * * *'
  form.interval_seconds = r.interval_seconds ?? 3600
  form.enabled = r.enabled
  form.max_events_per_email = r.max_events_per_email
  dialogVisible.value = true
}

async function onSave() {
  form.recipients = recipientsText.value
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (!form.recipients.length) {
    showToast('请填写至少一个收件人邮箱')
    return
  }
  if (!form.task_ids.length) {
    showToast('请选择至少一个分析任务')
    return
  }
  if (!form.event_types.length) {
    showToast('请选择至少一种事件类型')
    return
  }
  const data: RuleForm = {
    name: form.name,
    task_ids: form.task_ids,
    event_types: form.event_types,
    recipients: form.recipients,
    trigger_mode: form.trigger_mode,
    cron_expr: form.trigger_mode === 'scheduled' ? form.cron_expr || null : null,
    interval_seconds: form.trigger_mode === 'scheduled' ? form.interval_seconds || null : null,
    enabled: form.enabled,
    max_events_per_email: form.max_events_per_email,
  }
  try {
    if (editing.value) {
      await updateRuleApi(editing.value.id, data)
    } else {
      await createRuleApi(data)
    }
    showToast('保存成功')
    dialogVisible.value = false
    await loadRules()
  } catch { /* handled */ }
}

async function onDelete(r: PushRule) {
  if (!confirm(`确认删除推送规则「${r.name}」？`)) return
  await deleteRuleApi(r.id)
  showToast('已删除')
  await loadRules()
}

async function onToggle(r: PushRule) {
  await updateRuleApi(r.id, { enabled: !r.enabled })
  showToast(!r.enabled ? '已启用' : '已禁用')
  await loadRules()
}

async function onTrigger(r: PushRule) {
  await triggerRuleApi(r.id)
  showToast('已提交推送，请稍后在历史中查看结果')
}

async function openHistory(r: PushRule) {
  historyRule.value = r
  historyVisible.value = true
  runs.value = []
  runs.value = await listRunsApi(r.id)
}

async function onSaveSmtp() {
  await putSmtpApi({
    host: smtp.host,
    port: smtp.port,
    use_tls: smtp.use_tls,
    use_ssl: smtp.use_ssl,
    username: smtp.username,
    password: smtp.password, // 空表示保留
    from_email: smtp.from_email,
    from_name: smtp.from_name,
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
</script>
