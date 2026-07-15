import axios, { type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

// The response interceptor unwraps `resp.data`, so request methods return the
// payload directly. The second generic of each method is therefore the payload type.
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
      // 403 is handled by the caller (page-level permission feedback); other
      // errors surface a toast here.
      ElMessage.error(typeof detail === 'string' ? detail : '请求失败')
    }
    return Promise.reject(error)
  },
)

export default request
