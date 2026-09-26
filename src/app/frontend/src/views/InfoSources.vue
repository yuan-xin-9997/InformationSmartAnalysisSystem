<template>
  <div>
    <div class="toolbar">
      <div class="stats"><strong>{{ sources.length }}</strong><span>个信息源</span></div>
      <div class="button-row">
        <button @click="load">刷新</button>
        <button class="primary" @click="openCreate">＋ 添加信息源</button>
      </div>
    </div>

    <div v-if="!sources.length" class="empty">
      <b>还没有信息源</b><span>添加一个官方网站、本地文件夹或 FreshRSS 信息源。</span>
    </div>
    <div v-else class="item-list">
      <article v-for="s in sources" :key="s.id" class="item-card">
        <div class="file-icon">{{ typeIcon(s.type) }}</div>
        <div class="grow">
          <div class="item-title">
            <h3>{{ s.name }}</h3>
            <span :class="['pill', s.status]">{{ typeLabel(s.type) }} · {{ s.status }}</span>
          </div>
          <p>{{ describe(s) }}</p>
          <div v-if="s.type === 'website' && s.site_status" class="meta" style="display:block">
            <div v-for="(state, url) in s.site_status" :key="url">
              {{ state.name }} · {{ state.status }} · {{ state.item_count }} 条 · {{ formatBeijing(state.last_sync_at) }}
              <span v-if="state.error" class="error">{{ state.error }}</span>
            </div>
          </div>
          <div class="meta">
            <span>{{ s.item_count }} 条</span>
            <span>同步于 {{ s.last_sync_at || '从未' }}</span>
            <span v-if="s.last_error" class="error">{{ s.last_error }}</span>
          </div>
        </div>
        <div class="actions">
          <button @click="onCheck(s.id)">检查</button>
          <button class="accent" @click="onSync(s.id)">同步</button>
          <button @click="openItems(s)">条目</button>
          <button @click="openEdit(s)">编辑</button>
          <button class="danger" @click="onDelete(s)">删除</button>
        </div>
      </article>
    </div>

    <div v-if="dialogVisible" class="modal" @click.self="dialogVisible = false">
      <form class="modal-card large" @submit.prevent="onSave">
        <div class="modal-head">
          <div><p class="eyebrow">INFO SOURCE</p><h2>{{ editing ? '编辑信息源' : '添加信息源' }}</h2></div>
          <button type="button" @click="dialogVisible = false">×</button>
        </div>
        <label>名称<input v-model.trim="form.name" required /></label>
        <div class="form-grid">
          <label>类型
            <select v-model="form.type" :disabled="!!editing">
              <option v-for="t in typeSpecs" :key="t.type" :value="t.type">{{ typeLabel(t.type) }}</option>
            </select>
          </label>
          <label>必填字段
            <input :value="requiredHint" disabled style="background:#f2f5fa" />
          </label>
        </div>
        <div v-if="form.type === 'website'">
          <h3>网站来源</h3>
          <div v-for="(site, index) in sites" :key="index" class="form-grid" style="margin-bottom:12px">
            <label>来源名称<input v-model.trim="site.name" required /></label>
            <label>资讯栏目 URL<input v-model.trim="site.url" type="url" required /></label>
            <label>链接选择器<input v-model.trim="site.link_selector" placeholder="a" /></label>
            <label>正文选择器<input v-model.trim="site.content_selector" placeholder="article, main, body" /></label>
            <label>抓取模式<select v-model="site.mode"><option value="auto">auto</option><option value="http">http</option><option value="browser">browser</option></select></label>
            <label>条目上限<input v-model.number="site.max_items" type="number" min="1" max="500" /></label>
            <button type="button" @click="sites.splice(index, 1)">删除网站</button>
          </div>
          <button type="button" @click="addSite">＋ 添加网站</button>
        </div>
        <label v-else>配置（JSON）
          <textarea v-model="configText" rows="9" placeholder="请输入 JSON 配置"></textarea>
        </label>
        <div class="modal-actions">
          <button type="button" @click="dialogVisible = false">取消</button>
          <button class="primary">保存</button>
        </div>
      </form>
    </div>

    <div v-if="itemsVisible" class="modal" @click.self="itemsVisible = false">
      <div class="modal-card large">
        <div class="modal-head">
          <div><p class="eyebrow">ITEMS</p><h2>条目 - {{ currentSource?.name }}</h2></div>
          <button type="button" @click="itemsVisible = false">×</button>
        </div>
        <div class="toolbar" style="margin-bottom:12px">
          <div class="stats">
            <strong>{{ counts.total }}</strong>
            <span>条（共 {{ counts.all }}｜已分析 {{ counts.analyzed }} / 未分析 {{ counts.unanalyzed }}）</span>
          </div>
          <div class="button-row">
            <select v-if="currentSource?.type === 'website'" v-model="siteFilter" style="width:auto" @change="onFilterChange">
              <option value="">全部网站</option>
              <option v-for="site in currentSites" :key="site.url" :value="site.url">{{ site.name }}</option>
            </select>
            <select v-model="filter" style="width:auto" @change="onFilterChange">
              <option value="">全部</option>
              <option value="analyzed">已分析</option>
              <option value="unanalyzed">未分析</option>
            </select>
            <select v-model.number="pageSize" style="width:auto" @change="onPageSizeChange">
              <option :value="50">50/页</option>
              <option :value="100">100/页</option>
              <option :value="200">200/页</option>
            </select>
          </div>
        </div>
        <div v-if="!items.length" class="empty compact">无符合条件的条目</div>
        <table v-else>
          <thead><tr><th>标题</th><th>网站来源</th><th>已分析</th><th>发布时间</th></tr></thead>
          <tbody>
            <tr v-for="it in items" :key="it.id">
              <td>{{ it.title || '(无标题)' }}</td>
              <td>{{ it.site_name || '-' }}</td>
              <td><span :class="['pill', it.analyzed ? 'ok' : '']">{{ it.analyzed ? '是' : '否' }}</span></td>
              <td>{{ it.published_at || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <div class="toolbar" style="margin-top:12px">
          <span class="muted" style="font-size:12px">第 {{ page }} / {{ totalPages }} 页</span>
          <div class="button-row">
            <button :disabled="page <= 1" @click="prevPage">上一页</button>
            <button :disabled="page >= totalPages" @click="nextPage">下一页</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { showToast } from '@/composables/toast'
import {
  listSourcesApi, createSourceApi, updateSourceApi, deleteSourceApi,
  checkSourceApi, syncSourceApi, listItemsApi, countItemsApi, getTypesApi,
  type InfoSource, type InfoItemBrief, type SourceTypeSpec,
} from '@/api/sources'

const sources = ref<InfoSource[]>([])
const typeSpecs = ref<SourceTypeSpec[]>([])
const dialogVisible = ref(false)
const editing = ref<InfoSource | null>(null)
const form = reactive({ name: '', type: 'local_folder' })
const configText = ref('{\n  "folder_path": ""\n}')
type WebsiteSite = { name: string; url: string; link_selector: string; content_selector: string; mode: string; max_items: number }
const sites = ref<WebsiteSite[]>([])
const siteFilter = ref('')
const currentSites = computed(() => currentSource.value ? readSites(currentSource.value.config) : [])
function readSites(config: Record<string, unknown>): WebsiteSite[] {
  const raw = Array.isArray(config.sites) ? config.sites : config.url ? [{ ...config, name: config.name || new URL(String(config.url)).hostname }] : []
  return raw.map((s: Record<string, unknown>) => ({ name: String(s.name || ''), url: String(s.url || ''), link_selector: String(s.link_selector || ''), content_selector: String(s.content_selector || ''), mode: String(s.mode || 'auto'), max_items: Number(s.max_items || 20) }))
}
function addSite() { sites.value.push({ name: '', url: '', link_selector: '', content_selector: '', mode: 'auto', max_items: 20 }) }
const itemsVisible = ref(false)
const currentSource = ref<InfoSource | null>(null)
const items = ref<InfoItemBrief[]>([])
const page = ref(1)
const pageSize = ref(50)
const filter = ref<'' | 'analyzed' | 'unanalyzed'>('')
const counts = ref({ total: 0, all: 0, analyzed: 0, unanalyzed: 0 })

watch(() => form.type, (type) => {
  if (type === 'website' && !sites.value.length) addSite()
})

const requiredHint = computed(() => {
  const spec = typeSpecs.value.find((t) => t.type === form.type)
  return spec ? spec.required_keys.join(', ') : ''
})

onMounted(async () => {
  await load()
  typeSpecs.value = await getTypesApi()
})

async function load() {
  sources.value = await listSourcesApi()
}

function formatBeijing(value: string | null): string {
  if (!value) return '未同步'
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value))
}

function typeLabel(t: string) {
  return { website: '官方网站', local_folder: '本地文件夹', freshrss: 'FreshRSS' }[t] || t
}
function typeIcon(t: string) {
  return { website: '网', local_folder: '夹', freshrss: '阅' }[t] || '源'
}
function describe(s: InfoSource) {
  const c = s.config || {}
  if (s.type === 'website') return readSites(c).map(site => site.name).join('、')
  if (s.type === 'local_folder') return String(c.folder_path || '')
  if (s.type === 'freshrss') return String(c.base_url || '')
  return ''
}

function openCreate() {
  editing.value = null
  form.name = ''
  form.type = 'local_folder'
  configText.value = '{\n  "folder_path": ""\n}'
  sites.value = []
  dialogVisible.value = true
}
function openEdit(s: InfoSource) {
  editing.value = s
  form.name = s.name
  form.type = s.type
  configText.value = JSON.stringify(s.config, null, 2)
  sites.value = s.type === 'website' ? readSites(s.config) : []
  dialogVisible.value = true
}

async function onSave() {
  let config: Record<string, unknown>
  try {
    config = form.type === 'website' ? { sites: sites.value.map(site => ({ ...site })) } : JSON.parse(configText.value)
  } catch {
    showToast('配置不是合法的 JSON')
    return
  }
  try {
    if (editing.value) {
      await updateSourceApi(editing.value.id, { name: form.name, config })
    } else {
      await createSourceApi({ name: form.name, type: form.type, config })
    }
    showToast('保存成功')
    dialogVisible.value = false
    await load()
  } catch {
    /* 吐司由拦截器处理 */
  }
}

async function onDelete(s: InfoSource) {
  if (!confirm(`确认删除信息源「${s.name}」？`)) return
  await deleteSourceApi(s.id)
  showToast('已删除')
  await load()
}

async function onCheck(id: number) {
  try {
    const st = await checkSourceApi(id)
    showToast(st.message || st.status)
    await load()
  } catch {
    /* handled */
  }
}

async function onSync(id: number) {
  const { run_id } = await syncSourceApi(id)
  showToast(`已提交同步，运行 ID: ${run_id}`)
  setTimeout(load, 1500)
}

const totalPages = computed(() => Math.max(1, Math.ceil(counts.value.total / pageSize.value)))

function analyzedParam(): boolean | undefined {
  return filter.value === 'analyzed' ? true : filter.value === 'unanalyzed' ? false : undefined
}

async function loadItems() {
  if (!currentSource.value) return
  const a = analyzedParam()
  const offset = (page.value - 1) * pageSize.value
  ;[items.value, counts.value] = await Promise.all([
    listItemsApi(currentSource.value.id, pageSize.value, offset, a, siteFilter.value || undefined),
    countItemsApi(currentSource.value.id, a, siteFilter.value || undefined),
  ])
}

async function openItems(s: InfoSource) {
  currentSource.value = s
  page.value = 1
  pageSize.value = 50
  filter.value = ''
  siteFilter.value = ''
  await loadItems()
  itemsVisible.value = true
}

function onFilterChange() {
  page.value = 1
  loadItems()
}
function onPageSizeChange() {
  page.value = 1
  loadItems()
}
function prevPage() {
  if (page.value > 1) {
    page.value--
    loadItems()
  }
}
function nextPage() {
  if (page.value < totalPages.value) {
    page.value++
    loadItems()
  }
}
</script>
