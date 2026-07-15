import request from './request'

export interface RuntimeInfo {
  started_at: string | null
  pid: number
  version: string
  host: string
  port: number
  db_path: string
  log_dir: string
  data_dir: string
  python_version: string
}

export interface ConfigResponse {
  config: Record<string, unknown>
  runtime: RuntimeInfo
}

export const getConfigApi = () => request.get<unknown, ConfigResponse>('/api/config')
