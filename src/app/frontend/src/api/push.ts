import request from './request'

export interface SmtpConfig {
  host: string
  port: number
  use_tls: boolean
  use_ssl: boolean
  username: string
  from_email: string
  from_name: string
  password: string // 脱敏展示值
}

export interface PushRun {
  id: number
  rule_id: number
  trigger_mode: string
  recipients: string[]
  event_count: number
  status: 'succeeded' | 'failed' | 'no_new'
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

// ---- SMTP config（全局邮件通道，归属「任务分析」页）----
export const getSmtpApi = () => request.get<unknown, SmtpConfig>('/api/push/smtp')

export const putSmtpApi = (data: {
  host: string
  port: number
  use_tls: boolean
  use_ssl: boolean
  username: string
  password: string // 空表示保留旧密码
  from_email: string
  from_name: string
}) => request.put<unknown, SmtpConfig>('/api/push/smtp', data)

export const testSmtpApi = (to_email: string) =>
  request.post<unknown, { ok: boolean; error: string | null }>('/api/push/smtp/test', { to_email })
