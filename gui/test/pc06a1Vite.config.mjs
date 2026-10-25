// 仅隔离验收代理；不改生产开发配置，也不接触默认8000服务。
import original from '../vite.config.ts'
export default {
  ...original,
  server: {host:'127.0.0.1', port:Number(process.env.PC06A1_GUI_PORT||5188), strictPort:true,
    proxy: {'/api': {target:process.env.PC06A1_API_TARGET||'http://127.0.0.1:18086', changeOrigin:true, ws:true}}},
}
