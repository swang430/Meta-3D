import { mergeConfig } from 'vite'
import config from './vite.config'

// 本片专用临时Mock库，不连接用户默认API。
export default mergeConfig(config, { server: { proxy: {
  '/api/v1/ota': { target: 'http://127.0.0.1:18106' },
  '/api/v1/ws': { target: 'http://127.0.0.1:18106', ws: true },
  '/api': { target: 'http://127.0.0.1:18106' },
} } })
