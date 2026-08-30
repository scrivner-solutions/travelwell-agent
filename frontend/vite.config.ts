/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig(({ mode }) => ({
  plugins: [
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // Push, richer caching, and install education land in Phase 6; this is
      // the minimum for an installable shell.
      manifest: {
        name: 'TravelWell',
        short_name: 'TravelWell',
        description: 'Your proactive travel wellness agent',
        display: 'standalone',
        start_url: '/',
        theme_color: '#185FA5',
        background_color: '#F4F7FB',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icons/icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // config.json is written at container start by entrypoint.sh and must
        // never be served stale from the precache.
        globIgnores: ['config.json'],
        navigateFallback: '/index.html',
        // /api navigations (OAuth start/callback redirects) must reach the
        // server, never the SPA shell.
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
  ],
  resolve: {
    alias: { '@': '/src' },
  },
  server: {
    // Dev only: same-origin /api (per the runtime config default) forwards to
    // the local backend, mirroring how nginx fronts it in deployment. Point
    // it at a deployed backend via frontend/.env.local:
    //   API_PROXY_TARGET=https://travelwell-backend-<hash>.run.app
    proxy: {
      '/api': {
        target: loadEnv(mode, '.', '').API_PROXY_TARGET ?? 'http://localhost:8000',
        // Cloud Run's front end routes by Host header; localhost:5173 404s.
        changeOrigin: true,
        // A private Cloud Run target needs an identity token the browser cannot
        // send. Tokens expire hourly, so pass one per run rather than storing it:
        //   API_PROXY_AUTH_TOKEN=$(gcloud auth print-identity-token) npm run dev
        headers: loadEnv(mode, '.', '').API_PROXY_AUTH_TOKEN
          ? {
              Authorization: `Bearer ${loadEnv(mode, '.', '').API_PROXY_AUTH_TOKEN}`,
            }
          : undefined,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Unit tests only. e2e/ belongs to Playwright's runner (playwright.config
    // testDir), which vitest's default **/*.spec.ts glob would otherwise
    // collect and crash on.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
}))
