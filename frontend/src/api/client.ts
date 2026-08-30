import createClient from 'openapi-fetch'
import type { paths, components } from './schema'
import { loadRuntimeConfig } from '@/lib/config'

export type Problem = components['schemas']['ProblemOut']

/**
 * Thrown for every non-2xx response so TanStack Query sees a real failure.
 * `problem` carries the RFC 9457 body when the server sent one; `status` lets
 * guards distinguish 401 (redirect to sign-in) from degraded backends.
 */
export class ApiError extends Error {
  readonly status: number
  readonly problem: Problem | undefined

  constructor(status: number, problem?: Problem) {
    super(problem?.title ?? `Request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.problem = problem
  }
}

let client: ReturnType<typeof createClient<paths>> | null = null

// Async so every call is a retry point for the runtime config: a config.json
// fetch that failed at launch is retried here instead of bricking the app.
export async function api() {
  const { apiBaseUrl } = await loadRuntimeConfig()
  client ??= createClient<paths>({
    baseUrl: `${apiBaseUrl}/api/v1`,
    credentials: 'include',
  })
  return client
}

export function throwOnError<T>(result: {
  data?: T
  error?: unknown
  response: Response
}): T {
  if (result.error !== undefined || !result.response.ok) {
    throw new ApiError(result.response.status, result.error as Problem | undefined)
  }
  return result.data as T
}
