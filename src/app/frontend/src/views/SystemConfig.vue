<template>
  <div v-if="data">
    <div class="settings-grid">
      <div class="panel">
        <div class="panel-head"><h2>运行时信息</h2><span>只读</span></div>
        <dl>
          <dt>服务启动时间</dt><dd>{{ data.runtime.started_at || '-' }}</dd>
          <dt>进程 PID</dt><dd>{{ data.runtime.pid }}</dd>
          <dt>版本</dt><dd>{{ data.runtime.version }}</dd>
          <dt>Python</dt><dd>{{ data.runtime.python_version }}</dd>
          <dt>监听</dt><dd>{{ data.runtime.host }}:{{ data.runtime.port }}</dd>
          <dt>数据库</dt><dd>{{ data.runtime.db_path }}</dd>
          <dt>日志目录</dt><dd>{{ data.runtime.log_dir }}</dd>
          <dt>数据目录</dt><dd>{{ data.runtime.data_dir }}</dd>
        </dl>
      </div>
      <div class="panel">
        <div class="panel-head"><h2>配置文件</h2><span>敏感字段已脱敏</span></div>
        <pre class="content-pre">{{ configText }}</pre>
      </div>
    </div>
  </div>
  <div v-else class="empty">正在加载配置…</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getConfigApi, type ConfigResponse } from '@/api/config'

const data = ref<ConfigResponse | null>(null)

const configText = computed(() => (data.value ? JSON.stringify(data.value.config, null, 2) : ''))

onMounted(async () => {
  data.value = await getConfigApi()
})
</script>
