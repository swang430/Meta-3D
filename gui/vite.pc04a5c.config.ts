import { mergeConfig } from 'vite'
import config from './vite.config'

// 5c专用新SQLite/Mock服务；三个代理全部覆盖，禁止漏回用户8000。
export default mergeConfig(config, { server: { proxy: {
  '/api/v1/ota': { target: 'http://127.0.0.1:18116' },
  '/api/v1/ws': { target: 'http://127.0.0.1:18116', ws: true },
  '/api': { target: 'http://127.0.0.1:18116' },
} } })
