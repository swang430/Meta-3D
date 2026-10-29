import {defineConfig, mergeConfig} from 'vite';
import base from '../vite.config';

// 本片三条代理全部指向新 SQLite 的专用 API，不访问用户现有服务。
export default mergeConfig(base, defineConfig({server:{host:'127.0.0.1',port:18127,strictPort:true,
  proxy:{'/api/v1/ws':{target:'http://127.0.0.1:18126',ws:true},
    '/api/v1/ota':{target:'http://127.0.0.1:18126'},
    '/api':{target:'http://127.0.0.1:18126'}}}}));
