import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

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
      },
      // Channel Engine Service proxy
      '/api/v1/ota': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      // REST API proxy
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})