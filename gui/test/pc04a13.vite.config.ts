import {defineConfig,mergeConfig} from 'vite'
import base from '../vite.config'
// 仅本片新隔离SQLite服务，不连接用户8000端口。
export default mergeConfig(base,defineConfig({server:{host:'127.0.0.1',port:15513,strictPort:true,
 proxy:{'/api/v1/ws':{target:'http://127.0.0.1:18513',ws:true},
 '/api/v1/ota':{target:'http://127.0.0.1:18513'},'/api':{target:'http://127.0.0.1:18513'}}}}))
