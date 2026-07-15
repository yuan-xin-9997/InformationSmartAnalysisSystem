import { ref } from 'vue'

// 全局吐司，替代 Element Plus 的 ElMessage。
const message = ref('')
let timer: ReturnType<typeof setTimeout> | undefined

export function showToast(msg: string) {
  message.value = msg
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    message.value = ''
  }, 3500)
}

export function useToast() {
  return { message }
}
