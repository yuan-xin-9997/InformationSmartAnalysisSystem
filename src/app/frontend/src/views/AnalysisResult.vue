<template>
  <div>
    <div class="toolbar">
      <el-select v-model="taskId" placeholder="按任务筛选" clearable style="width: 220px" @change="load">
        <el-option v-for="t in tasks" :key="t.id" :label="t.name" :value="t.id" />
      </el-select>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="results" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.result_type === 'aggregate' ? 'warning' : ''">
            {{ row.result_type === 'aggregate' ? '汇总' : '逐条' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="source_name" label="信息源" width="140" />
      <el-table-column label="信息项" width="90">
        <template #default="{ row }">{{ row.info_item_id ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="content" label="分析内容" show-overflow-tooltip />
      <el-table-column label="生成时间" width="180">
        <template #default="{ row }">{{ row.created_at }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link @click="openContent(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="contentVisible" title="分析内容" width="720px">
      <pre class="content-pre">{{ currentContent }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  listTasksApi,
  listAllResultsApi,
  listTaskResultsApi,
  type AnalysisTask,
  type AnalysisResult,
} from '@/api/tasks'

const route = useRoute()
const tasks = ref<AnalysisTask[]>([])
const taskId = ref<number | undefined>(undefined)
const results = ref<AnalysisResult[]>([])
const contentVisible = ref(false)
const currentContent = ref('')

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

function openContent(row: AnalysisResult) {
  currentContent.value = row.content
  contentVisible.value = true
}
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
}
.content-pre {
  white-space: pre-wrap;
  word-break: break-word;
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  max-height: 60vh;
  overflow: auto;
  font-family: inherit;
}
</style>
