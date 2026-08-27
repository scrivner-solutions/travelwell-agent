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
