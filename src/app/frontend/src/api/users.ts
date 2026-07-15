import request from './request'

export interface UserOut {
  id: number
  username: string
  role: string
  created_at: string
}

export interface PageDefinition {
  key: string
  label: string
  grantable: boolean
}

export const listUsersApi = () => request.get<unknown, UserOut[]>('/api/users')
export const listPagesApi = () => request.get<unknown, PageDefinition[]>('/api/users/pages')
export const getPermissionsApi = (userId: number) =>
  request.get<unknown, string[]>(`/api/users/${userId}/permissions`)
export const setPermissionsApi = (userId: number, pageKeys: string[]) =>
  request.put<unknown, string[]>(`/api/users/${userId}/permissions`, { page_keys: pageKeys })
