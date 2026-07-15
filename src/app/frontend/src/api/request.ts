import axios, { type AxiosResponse } from 'axios'
import { showToast } from '@/composables/toast'

// 响应拦截器解包 resp.data，故请求方法直接返回业务数据。
const request = axios.create({
  baseURL: '',
  timeout: 60000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('isas_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (resp: AxiosResponse) => resp.data,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail || error.message
    if (status === 401) {
      localStorage.removeItem('isas_token')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    } else if (status !== 403) {
      // 403 由页面层处理（页面级权限反馈），其余错误弹吐司。
      showToast(typeof detail === 'string' ? detail : '请求失败')
    }
    return Promise.reject(error)
  },
)

export default request
