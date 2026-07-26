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

export type TriggerMode = 'on_run' | 'scheduled' | 'manual'

export interface PushRule {
  id: number
  name: string
  channel: string
  task_ids: number[]
  event_types: string[]
  recipients: string[]
  trigger_mode: TriggerMode
  cron_expr: string | null
  interval_seconds: number | null
  enabled: boolean
  last_pushed_result_id: number | null
  max_events_per_email: number
  created_at: string
  updated_at: string
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

// ---- SMTP config ----
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

// ---- Push rules ----
export interface RuleForm {
  name: string
  task_ids: number[]
  event_types: string[]
  recipients: string[]
  trigger_mode: TriggerMode
  cron_expr: string | null
  interval_seconds: number | null
  enabled: boolean
  max_events_per_email: number
}

export const listRulesApi = () => request.get<unknown, PushRule[]>('/api/push/rules')

export const createRuleApi = (data: RuleForm) =>
  request.post<unknown, PushRule>('/api/push/rules', data)

export const updateRuleApi = (id: number, data: Partial<RuleForm>) =>
  request.put<unknown, PushRule>(`/api/push/rules/${id}`, data)

export const deleteRuleApi = (id: number) =>
  request.delete<unknown, unknown>(`/api/push/rules/${id}`)

export const triggerRuleApi = (id: number) =>
  request.post<unknown, { ok: boolean }>(`/api/push/rules/${id}/trigger`)

export const listRunsApi = (ruleId: number) =>
  request.get<unknown, PushRun[]>(`/api/push/rules/${ruleId}/runs`)
