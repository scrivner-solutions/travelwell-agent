/**
 * Runtime configuration, kept on the prototype's proven pattern: entrypoint.sh
 * writes /config.json into the nginx html dir at container start, so one image
 * serves every environment. In dev, Vite serves public/config.json.
 */
export interface RuntimeConfig {
  apiBaseUrl: string
}

let loaded: RuntimeConfig | null = null

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
  if (loaded) return loaded
  const res = await fetch('/config.json', { cache: 'no-store' })
  if (!res.ok) {
    throw new Error(`config.json unavailable (${res.status})`)
  }
  const raw = (await res.json()) as Record<string, unknown>
  loaded = {
    // Key name matches what entrypoint.sh has always emitted.
    apiBaseUrl: typeof raw.VITE_API_BASE_URL === 'string' ? raw.VITE_API_BASE_URL : '',
  }
  return loaded
}

export function runtimeConfig(): RuntimeConfig {
  if (!loaded) {
    throw new Error('runtimeConfig() called before loadRuntimeConfig() resolved')
  }
  return loaded
}
