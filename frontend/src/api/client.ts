import createClient from 'openapi-fetch'
import type { paths, components } from './schema'
import { runtimeConfig } from '@/lib/config'

export type Problem = components['schemas']['Problem']

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

export function api() {
  client ??= createClient<paths>({
    baseUrl: `${runtimeConfig().apiBaseUrl}/api/v1`,
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
