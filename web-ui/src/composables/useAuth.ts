import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

export function useAuth() {
  const router = useRouter()
  const store = useAuthStore()

  const username = computed(() => store.username)
  const isAuthenticated = computed(() => store.isAuthenticated)

  function logout() {
    store.clearAuthentication()

    // Redirect to login if using router
    if (router) {
      router.push('/login')
    } else {
      window.location.href = '/login'
    }
  }

  async function login(user: string, pass: string): Promise<boolean> {
    return store.login(user, pass)
  }

  return {
    username,
    isAuthenticated,
    login,
    logout,
  }
}
