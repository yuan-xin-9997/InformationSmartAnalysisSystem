import { defineStore } from 'pinia'
import { getMeApi, loginApi, type UserOut } from '@/api/auth'

const TOKEN_KEY = 'isas_token'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: null as UserOut | null,
    pages: [] as string[],
  }),
  getters: {
    isAdmin: (state) => state.user?.role === 'admin',
    isAuthed: (state) => !!state.token,
  },
  actions: {
    async login(username: string, password: string) {
      const data = await loginApi(username, password)
      this.token = data.access_token
      this.user = data.user
      this.pages = data.pages
      localStorage.setItem(TOKEN_KEY, this.token)
    },
    async fetchMe() {
      try {
        const data = await getMeApi()
        this.user = data.user
        this.pages = data.pages
      } catch {
        this._clear()
      }
    },
    logout() {
      this._clear()
    },
    _clear() {
      this.token = ''
      this.user = null
      this.pages = []
      localStorage.removeItem(TOKEN_KEY)
    },
  },
})
