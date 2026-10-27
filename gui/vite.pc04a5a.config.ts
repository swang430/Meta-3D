import { mergeConfig } from 'vite'
import config from './vite.config'

// 专用夹具代理；不接触用户 8000，也不改默认配置。
export default mergeConfig(config, {
  server: { proxy: {
    '/api/v1/ws': { target: 'http://127.0.0.1:18105', ws: true },
    '/api': { target: 'http://127.0.0.1:18105' },
  } },
})
