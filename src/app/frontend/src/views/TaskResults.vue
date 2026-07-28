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
            <details v-for="r in resultsByRun[run.id]" :key="r.id" style="margin-bottom:6px" @toggle="onResultToggle(r, $event)">
              <summary style="cursor:pointer">
                <span :class="['pill', r.result_type === 'aggregate' ? 'warning' : 'ok']">{{ r.result_type === 'aggregate' ? '汇总' : '逐条' }}</span>
                {{ r.source_name || '未知源' }} · {{ r.created_at }}
              </summary>
              <div style="margin-top:8px">
                <!-- aggregate 或 source_file 缺失：仅文字结果 -->
                <template v-if="!r.source_file">
                  <div class="markdown" v-html="renderMd(r.content)"></div>
                </template>
                <!-- per_item 三段式 -->
                <template v-else>
                  <!-- ① 文件信息 -->
                  <section class="result-section">
                    <p class="eyebrow">文件信息</p>
                    <div class="file-info-row">
                      <button type="button" class="link-button" @click="openPreview(r)">{{ r.source_file.filename }}</button>
                      <span class="muted file-path" :title="r.source_file.file_path">{{ r.source_file.file_path }}</span>
                    </div>
                  </section>
                  <!-- ② 文章基本信息 + 图表 -->
                  <section class="result-section">
                    <p class="eyebrow">文章基本信息</p>
                    <dl>
                      <template v-if="r.source_file.title"><dt>标题</dt><dd>{{ r.source_file.title }}</dd></template>
                      <template v-if="r.source_file.author"><dt>作者</dt><dd>{{ r.source_file.author }}</dd></template>
                      <template v-if="r.source_file.author_affiliation"><dt>作者单位</dt><dd>{{ r.source_file.author_affiliation }}</dd></template>
                      <template v-if="r.source_file.published_at"><dt>发布时间</dt><dd>{{ r.source_file.published_at }}</dd></template>
                      <template v-if="r.source_file.page_count != null"><dt>页数</dt><dd>{{ r.source_file.page_count }}</dd></template>
                      <template v-if="!r.source_file.title && !r.source_file.author && !r.source_file.author_affiliation && !r.source_file.published_at && r.source_file.page_count == null"><dt>—</dt><dd class="muted">无元数据</dd></template>
                    </dl>
                    <div v-if="r.source_file.figures.length" class="figure-gallery">
                      <p class="eyebrow" style="margin-top:12px">图表（{{ r.source_file.figures.length }}）</p>
                      <div class="figure-row">
                        <img
                          v-for="(url, idx) in figureUrlsByResult[r.id] || []"
                          :key="idx"
                          :src="url"
                          class="figure-thumb"
                          :alt="`图表 ${idx + 1}`"
                          @click="openFigureViewer(url)"
                        />
                        <span v-if="!figureUrlsByResult[r.id] && figureLoading[r.id]" class="muted" style="font-size:12px">图表加载中...</span>
                        <span v-if="figureError[r.id]" class="error" style="font-size:12px">图表加载失败</span>
                      </div>
                    </div>
                  </section>
                  <!-- ③ 文字分析结果 -->
                  <section class="result-section">
                    <p class="eyebrow">分析结果</p>
                    <div class="markdown" v-html="renderMd(r.content)"></div>
                  </section>
                </template>
              </div>
            </details>
          </div>
        </div>
      </article>
    </div>

    <!-- 文件预览弹层 -->
    <div v-if="preview" class="modal" @click.self="closePreview">
      <div class="modal-card preview-card">
        <div class="modal-head">
          <div><p class="eyebrow">文件预览</p><h2 style="font-size:16px">{{ preview.filename }}</h2></div>
          <button type="button" @click="closePreview">×</button>
        </div>
        <div class="preview-body">
          <div v-if="preview.loading" class="muted">加载中...</div>
          <div v-else-if="preview.error" class="error">{{ preview.error }}</div>
          <iframe v-else-if="preview.kind === 'pdf' && preview.blobUrl" :src="preview.blobUrl" class="preview-iframe"></iframe>
          <div v-else-if="preview.kind === 'html' && preview.html" class="markdown" v-html="preview.html"></div>
          <div v-else-if="preview.kind === 'md' && preview.html" class="markdown" v-html="preview.html"></div>
          <pre v-else-if="preview.kind === 'txt' && preview.text !== null" class="content-pre">{{ preview.text }}</pre>
          <div v-else-if="preview.kind === 'docx'">
            <p class="muted" style="font-size:12px;margin:0 0 8px">已触发下载；以下为已抽取纯文本预览：</p>
            <pre v-if="preview.itemContent !== null" class="content-pre">{{ preview.itemContent || '（无纯文本内容）' }}</pre>
          </div>
          <div v-else class="muted">不支持预览此文件类型</div>
        </div>
      </div>
    </div>

    <!-- 图表大图弹层 -->
    <div v-if="figureViewerUrl" class="modal" @click.self="figureViewerUrl = null">
      <div class="modal-card preview-card" style="padding:14px">
        <div class="modal-head">
          <div><p class="eyebrow">图表</p></div>
          <button type="button" @click="figureViewerUrl = null">×</button>
        </div>
        <div class="preview-body" style="display:grid;place-items:center">
          <img :src="figureViewerUrl" class="figure-large" alt="图表大图" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DOMPurify from 'dompurify'
import {
  listTasksApi,
  listTaskResultsApi,
  listRunsApi,
  type AnalysisTaskDetail,
  type AnalysisResult,
  type TaskRun,
} from '@/api/tasks'
import { getFileBlobApi, getFigureBlobApi, getItemApi } from '@/api/sources'
import { renderMarkdown } from '@/utils/markdown'

const route = useRoute()
const router = useRouter()
const tasks = ref<AnalysisTaskDetail[]>([])
const taskId = ref<number>(Number(route.params.id))
const runs = ref<TaskRun[]>([])
const expandedRun = ref<number | null>(null)
const resultsByRun = reactive<Record<number, AnalysisResult[] | undefined>>({})
const renderMd = renderMarkdown

// 图表 blob URL 缓存：resultId -> 与 r.source_file.figures 顺序对齐的 objectURL 数组
const figureUrlsByResult = reactive<Record<number, string[]>>({})
const figureLoading = reactive<Record<number, boolean>>({})
const figureError = reactive<Record<number, boolean>>({})
// 图表大图查看器（复用缓存中的 URL，关闭时不 revoke，由缓存统一管理）
const figureViewerUrl = ref<string | null>(null)

// 文件预览弹层
type PreviewKind = 'pdf' | 'docx' | 'html' | 'md' | 'txt' | 'unknown'
interface PreviewState {
  resultId: number
  filename: string
  kind: PreviewKind
  loading: boolean
  error: string | null
  blobUrl: string | null
  text: string | null
  html: string | null
  itemContent: string | null
}
const preview = ref<PreviewState | null>(null)

onMounted(async () => {
  tasks.value = await listTasksApi()
  if (!tasks.value.find((t) => t.id === taskId.value) && tasks.value.length) {
    taskId.value = tasks.value[0].id
  }
  await loadRuns()
})

onBeforeUnmount(() => {
  closePreview()
  figureViewerUrl.value = null
  for (const key of Object.keys(figureUrlsByResult)) {
    for (const u of figureUrlsByResult[Number(key)]) URL.revokeObjectURL(u)
  }
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

// ---- 结果 <details> 展开：懒加载该结果所有图表 ----
async function onResultToggle(r: AnalysisResult, e: Event) {
  const details = e.target as HTMLDetailsElement
  if (!details.open) return
  if (!r.source_file || !r.source_file.figures.length) return
  if (figureUrlsByResult[r.id]) return // 已缓存
  if (!r.source_id || !r.info_item_id) return
  const sf = r.source_file
  const sourceId = r.source_id
  const itemId = r.info_item_id
  figureLoading[r.id] = true
  figureError[r.id] = false
  try {
    const results = await Promise.allSettled(
      sf.figures.map((fig) =>
        getFigureBlobApi(sourceId, itemId, fig.index).then((b) => URL.createObjectURL(b)),
      ),
    )
    const urls: string[] = []
    let failCount = 0
    results.forEach((res, i) => {
      if (res.status === 'fulfilled') {
        urls.push(res.value)
      } else {
        failCount++
        console.error('图表加载失败', sf.figures[i], res.reason)
      }
    })
    figureUrlsByResult[r.id] = urls
    if (failCount && !urls.length) figureError[r.id] = true
  } finally {
    figureLoading[r.id] = false
  }
}

// ---- 文件预览 ----
function suffixOf(filename: string): string {
  const i = filename.lastIndexOf('.')
  return i >= 0 ? filename.slice(i).toLowerCase() : ''
}

function kindOf(filename: string): PreviewKind {
  const s = suffixOf(filename)
  if (s === '.pdf') return 'pdf'
  if (s === '.docx') return 'docx'
  if (s === '.html' || s === '.htm') return 'html'
  if (s === '.md') return 'md'
  if (s === '.txt') return 'txt'
  return 'unknown'
}

function statusOf(err: unknown): number | undefined {
  return (err as { response?: { status?: number } })?.response?.status
}

async function openPreview(r: AnalysisResult) {
  if (!r.source_file || !r.source_id || !r.info_item_id) return
  const sf = r.source_file
  const sourceId = r.source_id
  const itemId = r.info_item_id
  closePreview() // 关闭上一个预览，释放其 blobUrl
  const kind = kindOf(sf.filename)
  preview.value = {
    resultId: r.id,
    filename: sf.filename,
    kind,
    loading: true,
    error: null,
    blobUrl: null,
    text: null,
    html: null,
    itemContent: null,
  }
  const p = preview.value
  try {
    if (kind === 'pdf') {
      const blob = await getFileBlobApi(sourceId, itemId)
      if (preview.value !== p) return // 已关闭/替换，丢弃结果，blob 由 GC 回收，避免泄漏 blobUrl
      p.blobUrl = URL.createObjectURL(blob)
    } else if (kind === 'docx') {
      const blob = await getFileBlobApi(sourceId, itemId)
      if (preview.value !== p) return // 已关闭/替换，不触发下载、不取 content
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = sf.filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      try {
        const item = await getItemApi(sourceId, itemId)
        if (preview.value !== p) return // 已关闭/替换，不写 itemContent 到 detached 代理
        p.itemContent = item.content || ''
      } catch {
        p.itemContent = ''
      }
    } else if (kind === 'html') {
      const blob = await getFileBlobApi(sourceId, itemId)
      if (preview.value !== p) return
      const text = await blob.text()
      if (preview.value !== p) return
      p.html = DOMPurify.sanitize(text)
    } else if (kind === 'md') {
      const blob = await getFileBlobApi(sourceId, itemId)
      if (preview.value !== p) return
      const text = await blob.text()
      if (preview.value !== p) return
      p.html = renderMarkdown(text)
    } else if (kind === 'txt') {
      const blob = await getFileBlobApi(sourceId, itemId)
      if (preview.value !== p) return
      const text = await blob.text()
      if (preview.value !== p) return
      p.text = text
    }
    // unknown: 无操作，弹层显示「不支持预览此文件类型」
  } catch (err) {
    const status = statusOf(err)
    if (status === 403) p.error = '无权访问该文件'
    else if (status === 404) p.error = '文件不存在或不支持预览'
    else p.error = '加载失败'
  } finally {
    p.loading = false
  }
}

function closePreview() {
  if (preview.value?.blobUrl) URL.revokeObjectURL(preview.value.blobUrl)
  preview.value = null
}

function openFigureViewer(url: string) {
  figureViewerUrl.value = url
}
</script>
