import request from './request'

export interface InfoSource {
  id: number
  name: string
  type: string
  config: Record<string, unknown>
  status: string
  last_sync_at: string | null
  last_error: string | null
  item_count: number
  created_at: string
  updated_at: string
}

export interface SourceTypeSpec {
  type: string
  required_keys: string[]
}

export interface SourceStatus {
  status: string
  message: string
  item_count: number
  last_sync_at: string | null
}

export interface InfoItemBrief {
  id: number
  source_id: number
  external_id: string
  title: string
  url: string | null
  published_at: string | null
  fetched_at: string
  analyzed: boolean
  created_at: string
}

export interface InfoItem extends InfoItemBrief {
  content: string
}

export const getTypesApi = () => request.get<unknown, SourceTypeSpec[]>('/api/info-sources/types')
export const listSourcesApi = () => request.get<unknown, InfoSource[]>('/api/info-sources')
export const createSourceApi = (data: { name: string; type: string; config: Record<string, unknown> }) =>
  request.post<unknown, InfoSource>('/api/info-sources', data)
export const getSourceApi = (id: number) => request.get<unknown, InfoSource>(`/api/info-sources/${id}`)
export const updateSourceApi = (id: number, data: Partial<{ name: string; config: Record<string, unknown> }>) =>
  request.put<unknown, InfoSource>(`/api/info-sources/${id}`, data)
export const deleteSourceApi = (id: number) => request.delete<unknown, unknown>(`/api/info-sources/${id}`)
export const checkSourceApi = (id: number) => request.post<unknown, SourceStatus>(`/api/info-sources/${id}/check`)
export const syncSourceApi = (id: number) => request.post<unknown, { run_id: number; status: string }>(`/api/info-sources/${id}/sync`)
export const getSourceStatusApi = (id: number) => request.get<unknown, SourceStatus>(`/api/info-sources/${id}/status`)
export const listItemsApi = (id: number, limit = 50, offset = 0) =>
  request.get<unknown, InfoItemBrief[]>(`/api/info-sources/${id}/items`, { params: { limit, offset } })
export const getItemApi = (sourceId: number, itemId: number) =>
  request.get<unknown, InfoItem>(`/api/info-sources/${sourceId}/items/${itemId}`)
