import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/client'

export function createQueryClient() {
  // A definitive 401 mid-session means the cookie expired or was revoked:
  // drop everything cached and land on sign-in. The _shell guard only covers
  // route entry; this covers every later query and mutation.
  // One-shot: clear() refetches mounted queries, which 401 again before the
  // navigation commits; the latch keeps the handler from re-entering.
  let redirecting = false
  const onAuthError = (error: unknown) => {
    if (!(error instanceof ApiError) || error.status !== 401 || redirecting) return
    if (window.location.pathname === '/sign-in') return
    redirecting = true
    client.clear()
    window.location.assign('/sign-in')
  }
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: onAuthError }),
    mutationCache: new MutationCache({ onError: onAuthError }),
    defaultOptions: {
      queries: {
        staleTime: 30 * 1000,
        refetchOnWindowFocus: true,
        retry: (failureCount, error) => {
          // 4xx responses are contract answers, not transient faults.
          if (error instanceof ApiError && error.status < 500) return false
          return failureCount < 2
        },
      },
    },
  })
  return client
}
