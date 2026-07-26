import request from './request'

export interface ScheduledJob {
  id: number
  task_id: number
  name: string
  mode: string
  trigger_type: string
  cron_expr: string | null
  interval_seconds: number | null
  enabled: boolean
  last_run_at: string | null
  last_run_status: string | null
  next_run_at: string | null
  created_at: string
  updated_at: string
}

export const listScheduledJobsApi = (params?: { task_id?: number; enabled?: boolean }) =>
  request.get<unknown, ScheduledJob[]>('/api/scheduled-jobs', { params })

export const createScheduledJobApi = (data: {
  task_id: number
  name: string
  mode: 'full' | 'incremental'
  trigger_type: 'cron' | 'interval'
  cron_expr?: string
  interval_seconds?: number
  enabled?: boolean
}) => request.post<unknown, ScheduledJob>('/api/scheduled-jobs', data)

export const updateScheduledJobApi = (id: number, data: Partial<{
  name: string
  mode: 'full' | 'incremental'
  trigger_type: 'cron' | 'interval'
  cron_expr?: string
  interval_seconds?: number
  enabled?: boolean
}>) => request.put<unknown, ScheduledJob>(`/api/scheduled-jobs/${id}`, data)

export const deleteScheduledJobApi = (id: number) =>
  request.delete<unknown, unknown>(`/api/scheduled-jobs/${id}`)

export const toggleScheduledJobApi = (id: number) =>
  request.post<unknown, ScheduledJob>(`/api/scheduled-jobs/${id}/toggle`)

export const runScheduledJobNowApi = (id: number) =>
  request.post<unknown, { run_id: number; status: string }>(`/api/scheduled-jobs/${id}/run`)
