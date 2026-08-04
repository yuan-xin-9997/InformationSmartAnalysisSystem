import request from './request'
import type { PushRun } from './push'

export interface TaskSourceOut {
  source_id: number
  source_name: string
  source_type: string
  source_status: string
  item_count: number
  last_analyzed_item_id: number | null
  last_analyzed_at: string | null
}

export type TriggerMode = 'on_run' | 'scheduled' | 'manual'

/** 1:1 定时分析配置（任务编辑弹窗「定时分析」区） */
export interface ScheduleConfig {
  enabled: boolean
  mode: 'full' | 'incremental'
  trigger_type: 'cron' | 'interval'
  cron_expr: string | null
  interval_seconds: number | null
}

export interface ScheduleConfigOut extends ScheduleConfig {
  id: number
  last_run_at: string | null
  last_run_status: string | null
  next_run_at: string | null
  created_at: string
  updated_at: string
}

/** 1:1 推送配置（任务编辑弹窗「推送配置」区） */
export interface PushConfig {
  enabled: boolean
  event_types: string[]
  recipients: string[]
  trigger_mode: TriggerMode
  cron_expr: string | null
  interval_seconds: number | null
  max_events_per_email: number
}

export interface PushConfigOut extends PushConfig {
  id: number
  last_pushed_result_id: number | null
  created_at: string
  updated_at: string
}

export interface AnalysisTask {
  id: number
  name: string
  description: string
  config: Record<string, unknown>
  created_at: string
  updated_at: string
  schedule: ScheduleConfigOut | null
  push: PushConfigOut | null
}

export interface AnalysisTaskDetail extends AnalysisTask {
  sources: TaskSourceOut[]
}

export interface InfoItemFigureOut {
  index: number
  url: string
  mime: string | null
  width: number | null
  height: number | null
}

export interface SourceFileOut {
  filename: string
  file_path: string
  title: string
  author: string | null
  author_affiliation: string | null
  published_at: string | null
  page_count: number | null
  file_url: string
  figures: InfoItemFigureOut[]
}

export interface AnalysisResult {
  id: number
  task_run_id: number
  task_id: number
  source_id: number | null
  source_name: string | null
  info_item_id: number | null
  result_type: string
  content: string
  created_at: string
  source_file: SourceFileOut | null
}

export interface TaskRun {
  id: number
  kind: string
  ref_id: number | null
  ref_name: string
  mode: string | null
  status: string
  started_at: string | null
  finished_at: string | null
  summary: string | null
  error: string | null
  created_at: string
}

export interface TaskRunDetail extends TaskRun {
  logs: { id: number; run_id: number | null; level: string; message: string; created_at: string }[]
}

export const listTasksApi = () => request.get<unknown, AnalysisTaskDetail[]>('/api/analysis-tasks')

export interface TaskSaveBody {
  name?: string
  description?: string
  config?: Record<string, unknown>
  source_ids?: number[]
  /** 传对象=upsert，传 null=删除该子配置，不传=不动 */
  schedule?: ScheduleConfig | null
  push?: PushConfig | null
}

export const createTaskApi = (data: TaskSaveBody & { name: string; source_ids: number[] }) =>
  request.post<unknown, AnalysisTaskDetail>('/api/analysis-tasks', data)
export const getTaskApi = (id: number) => request.get<unknown, AnalysisTaskDetail>(`/api/analysis-tasks/${id}`)
export const updateTaskApi = (id: number, data: TaskSaveBody) =>
  request.put<unknown, AnalysisTaskDetail>(`/api/analysis-tasks/${id}`, data)
export const deleteTaskApi = (id: number) => request.delete<unknown, unknown>(`/api/analysis-tasks/${id}`)
export const runTaskApi = (id: number, mode: 'full' | 'incremental' | 'custom') =>
  request.post<unknown, { run_id: number; status: string }>(`/api/analysis-tasks/${id}/run`, { mode })

// ---- 1:1 子配置动作 ----
export const runScheduleNowApi = (taskId: number) =>
  request.post<unknown, { run_id: number; status: string }>(`/api/analysis-tasks/${taskId}/schedule/run`)
export const triggerPushApi = (taskId: number) =>
  request.post<unknown, { ok: boolean }>(`/api/analysis-tasks/${taskId}/push/trigger`)
export const listPushRunsApi = (taskId: number) =>
  request.get<unknown, PushRun[]>(`/api/analysis-tasks/${taskId}/push/runs`)

export const listTaskResultsApi = (taskId: number, runId?: number) =>
  request.get<unknown, AnalysisResult[]>(`/api/analysis-tasks/${taskId}/results`, { params: { run_id: runId } })

export const listRunsApi = (params?: { kind?: string; ref_id?: number; status?: string; limit?: number }) =>
  request.get<unknown, TaskRun[]>('/api/task-center/runs', { params })
export const getRunApi = (id: number) => request.get<unknown, TaskRunDetail>(`/api/task-center/runs/${id}`)
export const deleteRunApi = (id: number) => request.delete<unknown, unknown>(`/api/task-center/runs/${id}`)
