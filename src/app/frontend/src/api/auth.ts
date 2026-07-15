import request from './request'

export interface UserOut {
  id: number
  username: string
  role: string
  created_at: string
}

export interface LoginResp {
  access_token: string
  token_type: string
  user: UserOut
  pages: string[]
}

export interface MeResp {
  user: UserOut
  pages: string[]
}

export const loginApi = (username: string, password: string) =>
  request.post<unknown, LoginResp>('/api/auth/login', { username, password })

export const getMeApi = () => request.get<unknown, MeResp>('/api/auth/me')
