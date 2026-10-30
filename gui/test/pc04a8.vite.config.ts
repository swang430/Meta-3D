import {defineConfig,mergeConfig} from 'vite'
import base from '../vite.config'
// 三条代理仅访问本片新 SQLite 的隔离服务。
export default mergeConfig(base,defineConfig({server:{host:'127.0.0.1',port:15148,strictPort:true,
  proxy:{'/api/v1/ws':{target:'http://127.0.0.1:18048',ws:true},
    '/api/v1/ota':{target:'http://127.0.0.1:18048'},
    '/api':{target:'http://127.0.0.1:18048'}}}}))
