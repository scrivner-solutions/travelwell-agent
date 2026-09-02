/**
 * Runtime configuration, kept on the prototype's proven pattern: entrypoint.sh
 * writes /config.json into the nginx html dir at container start, so one image
 * serves every environment. In dev, Vite serves public/config.json.
 */
export interface RuntimeConfig {
  apiBaseUrl: string
}

let pending: Promise<RuntimeConfig> | null = null

async function fetchConfig(): Promise<RuntimeConfig> {
  const res = await fetch('/config.json', { cache: 'no-store' })
  if (!res.ok) {
    throw new Error(`config.json unavailable (${res.status})`)
  }
  const raw = (await res.json()) as Record<string, unknown>
  return {
    // Key name matches what entrypoint.sh has always emitted.
    apiBaseUrl: typeof raw.VITE_API_BASE_URL === 'string' ? raw.VITE_API_BASE_URL : '',
  }
}

export function loadRuntimeConfig(): Promise<RuntimeConfig> {
  // A failed load is dropped so the next call retries; one bad fetch at
  // launch must not brick every api() call for the session.
  pending ??= fetchConfig().catch((error: unknown) => {
    pending = null
    throw error
  })
  return pending
}

/**
 * Absolute API URL for a full-page navigation. OAuth starts with a 302 to
 * Google, which fetch cannot follow (cross-origin) and cannot read (opaque),
 * so those routes are reached by navigating rather than by the typed client.
 */
export async function apiUrl(path: string): Promise<string> {
  // Same-origin fallback if config.json is unreachable; that is the deployed
  // default anyway.
  const { apiBaseUrl } = await loadRuntimeConfig().catch(() => ({ apiBaseUrl: '' }))
  return `${apiBaseUrl}/api/v1${path}`
}
