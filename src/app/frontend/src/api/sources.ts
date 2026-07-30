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
export const listItemsApi = (id: number, limit = 50, offset = 0, analyzed?: boolean) =>
  request.get<unknown, InfoItemBrief[]>(`/api/info-sources/${id}/items`, { params: { limit, offset, analyzed } })
export const countItemsApi = (
  id: number,
  analyzed?: boolean,
) =>
  request.get<unknown, { total: number; all: number; analyzed: number; unanalyzed: number }>(
    `/api/info-sources/${id}/items/count`,
    { params: { analyzed } },
  )
export const getItemApi = (sourceId: number, itemId: number) =>
  request.get<unknown, InfoItem>(`/api/info-sources/${sourceId}/items/${itemId}`)

/** 下载/预览 InfoItem 的源文件（PDF 内嵌 / docx 下载 / html·txt·md 文本）。鉴权头由 request 拦截器自动附加。 */
export const getFileBlobApi = (sourceId: number, itemId: number) =>
  request.get<unknown, Blob>(`/api/info-sources/${sourceId}/items/${itemId}/file`, { responseType: 'blob' })

/** 取某张图表的二进制（用于 <img> 缩略图/大图）。鉴权头由 request 拦截器自动附加。 */
export const getFigureBlobApi = (sourceId: number, itemId: number, index: number) =>
  request.get<unknown, Blob>(`/api/info-sources/${sourceId}/items/${itemId}/figures/${index}`, { responseType: 'blob' })

/** 手动重新抽取某 InfoItem 的元数据与图表。 */
export const reextractItemApi = (sourceId: number, itemId: number) =>
  request.post<unknown, { item_id: number; updated: boolean }>(`/api/info-sources/${sourceId}/items/${itemId}/reextract`)

export interface ItemsQueryParams {
  /** 仅返回指定 ID 的条目（用于取已选条目详情） */
  ids?: number[]
  /** 排除指定 ID（用于可浏览列表去重已选） */
  exclude_ids?: number[]
  /** 按白名单列排序：title/published_at/analyzed/created_at */
  sort_by?: string
  /** 升降序，仅 sort_by 有效时生效 */
  order?: 'asc' | 'desc'
  /** 标题模糊匹配（大小写不敏感） */
  keyword?: string
}

export interface ItemsQueryResp {
  items: InfoItemBrief[]
  total: number
}
export const queryItemsApi = (
  source_ids: number[],
  limit = 50,
  offset = 0,
  analyzed?: boolean,
  extra: ItemsQueryParams = {},
) =>
  request.post<unknown, ItemsQueryResp>('/api/info-sources/items/query', {
    source_ids,
    limit,
    offset,
    analyzed,
    ...extra,
  })
