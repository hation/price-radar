import { defineStore } from 'pinia'
import { wsService } from '@/services/websocket'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    username: localStorage.getItem('auth_username') as string | null,
    isLoggedIn: localStorage.getItem('auth_logged_in') === 'true',
  }),

  getters: {
    isAuthenticated: (state) => state.isLoggedIn,
  },

  actions: {
    setAuthenticated(user: string) {
      this.username = user
      this.isLoggedIn = true

      localStorage.setItem('auth_username', user)
      localStorage.setItem('auth_logged_in', 'true')

      wsService.start()
    },

    clearAuthentication() {
      this.username = null
      this.isLoggedIn = false

      localStorage.removeItem('auth_username')
      localStorage.removeItem('auth_logged_in')

      wsService.stop()
    },

    async login(user: string, pass: string): Promise<boolean> {
      try {
        const response = await fetch('/auth/status', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ username: user, password: pass }),
        })

        if (response.ok) {
          this.setAuthenticated(user)
          return true
        }
        return false
      } catch (e) {
        console.error('Login error', e)
        return false
      }
    },
  },
})
