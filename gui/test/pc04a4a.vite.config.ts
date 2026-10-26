import {defineConfig, mergeConfig} from 'vite';
import base from '../vite.config';
export default mergeConfig(base,defineConfig({server:{host:'127.0.0.1',port:5189,strictPort:true,
  proxy:{'/api/v1/ws':{target:'http://127.0.0.1:18094',ws:true},
    '/api':{target:'http://127.0.0.1:18094'},
    '/api/v1/ota':{target:'http://127.0.0.1:18094'}}}}));
