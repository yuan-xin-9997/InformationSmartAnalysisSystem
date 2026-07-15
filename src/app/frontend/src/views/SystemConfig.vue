<template>
  <div v-loading="loading">
    <el-card class="card">
      <template #header>运行时信息</template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="服务启动时间">{{ data?.runtime.started_at || '-' }}</el-descriptions-item>
        <el-descriptions-item label="进程 PID">{{ data?.runtime.pid }}</el-descriptions-item>
        <el-descriptions-item label="版本">{{ data?.runtime.version }}</el-descriptions-item>
        <el-descriptions-item label="Python">{{ data?.runtime.python_version }}</el-descriptions-item>
        <el-descriptions-item label="监听">{{ data?.runtime.host }}:{{ data?.runtime.port }}</el-descriptions-item>
        <el-descriptions-item label="数据库">{{ data?.runtime.db_path }}</el-descriptions-item>
        <el-descriptions-item label="日志目录">{{ data?.runtime.log_dir }}</el-descriptions-item>
        <el-descriptions-item label="数据目录">{{ data?.runtime.data_dir }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="card">
      <template #header>配置文件（app.json，敏感字段已脱敏）</template>
      <pre class="config-pre">{{ configText }}</pre>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getConfigApi, type ConfigResponse } from '@/api/config'

const data = ref<ConfigResponse | null>(null)
const loading = ref(true)

const configText = computed(() =>
  data.value ? JSON.stringify(data.value.config, null, 2) : '',
)

onMounted(async () => {
  try {
    data.value = await getConfigApi()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.card {
  margin-bottom: 16px;
}
.config-pre {
  white-space: pre-wrap;
  word-break: break-word;
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 13px;
  margin: 0;
}
</style>
