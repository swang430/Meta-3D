import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // WebSocket proxy - must be before /api to match first
      '/api/v1/ws': {
        target: 'http://localhost:8000',
        ws: true,
        changeOrigin: true,
        secure: false,
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, _res) => {
            // Suppress EPIPE/ECONNRESET errors - these are normal during reconnection
            if (err.message.includes('EPIPE') || err.message.includes('ECONNRESET')) {
              return
            }
            console.log('WebSocket proxy error:', err.message)
          })
          proxy.on('proxyReqWs', (_proxyReq, req, socket) => {
            console.log('WebSocket proxy request:', req.url)
            // Handle socket errors gracefully
            socket.on('error', (err: Error) => {
              if (err.message.includes('EPIPE') || err.message.includes('ECONNRESET')) {
                return // Suppress these common reconnection errors
              }
              console.log('WebSocket socket error:', err.message)
            })
          })
        },
      },
      // REST API proxy
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})