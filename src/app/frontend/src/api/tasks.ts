import request from './request'

export interface TaskSourceOut {
  source_id: number
  source_name: string
  source_type: string
  source_status: string
  item_count: number
  last_analyzed_item_id: number | null
  last_analyzed_at: string | null
}

export interface AnalysisTask {
  id: number
  name: string
  description: string
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface AnalysisTaskDetail extends AnalysisTask {
  sources: TaskSourceOut[]
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
export const createTaskApi = (data: {
  name: string
  description?: string
  config?: Record<string, unknown>
  source_ids: number[]
}) => request.post<unknown, AnalysisTaskDetail>('/api/analysis-tasks', data)
export const getTaskApi = (id: number) => request.get<unknown, AnalysisTaskDetail>(`/api/analysis-tasks/${id}`)
export const updateTaskApi = (id: number, data: Partial<{ name: string; description: string; config: Record<string, unknown>; source_ids: number[] }>) =>
  request.put<unknown, AnalysisTaskDetail>(`/api/analysis-tasks/${id}`, data)
export const deleteTaskApi = (id: number) => request.delete<unknown, unknown>(`/api/analysis-tasks/${id}`)
export const runTaskApi = (id: number, mode: 'full' | 'incremental' | 'custom') =>
  request.post<unknown, { run_id: number; status: string }>(`/api/analysis-tasks/${id}/run`, { mode })
export const listTaskResultsApi = (taskId: number, runId?: number) =>
  request.get<unknown, AnalysisResult[]>(`/api/analysis-tasks/${taskId}/results`, { params: { run_id: runId } })

export const listRunsApi = (params?: { kind?: string; status?: string; limit?: number }) =>
  request.get<unknown, TaskRun[]>('/api/task-center/runs', { params })
export const getRunApi = (id: number) => request.get<unknown, TaskRunDetail>(`/api/task-center/runs/${id}`)
export const deleteRunApi = (id: number) => request.delete<unknown, unknown>(`/api/task-center/runs/${id}`)

export const listAllResultsApi = (params?: { run_id?: number; task_id?: number; limit?: number }) =>
  request.get<unknown, AnalysisResult[]>('/api/analysis-results', { params })
