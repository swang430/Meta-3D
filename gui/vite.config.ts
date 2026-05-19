import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const transientProxyErrorCodes = new Set(['ECONNREFUSED', 'ETIMEDOUT', 'ECONNRESET'])

function configureProxyErrorLogger(serviceName: string) {
  return (proxy: { on: (event: 'error', handler: (err: Error & { code?: string }, req?: { url?: string }) => void) => void }) => {
    proxy.on('error', (err, req) => {
      if (err.code && transientProxyErrorCodes.has(err.code)) {
        console.warn(`[vite proxy] ${serviceName} target not ready yet: ${req?.url ?? 'unknown route'} (${err.code})`)
        return
      }

      console.error(`[vite proxy] ${serviceName} proxy error: ${req?.url ?? 'unknown route'}`, err)
    })
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // react-plotly.js expects plotly.js/dist/plotly, but we use the minified dist
      'plotly.js/dist/plotly': 'plotly.js-dist-min',
    },
  },
  server: {
    proxy: {
      // WebSocket proxy - must be before /api to match first
      '/api/v1/ws': {
        target: 'http://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
        secure: false,
        configure: configureProxyErrorLogger('API WebSocket'),
      },
      // Channel Engine Service proxy
      '/api/v1/ota': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        configure: configureProxyErrorLogger('ChannelEngine'),
      },
      // REST API proxy
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: configureProxyErrorLogger('API'),
      },
    },
  },
})
