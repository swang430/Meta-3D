import axios from 'axios'

// API Service 客户端 - 通过 Vite 代理连接到 FastAPI 后端 (8000)
// 使用 /api/* 代理规则而不是硬写地址，确保正确的请求转发
const calibrationClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000, // 校准操作可能需要更长时间
  headers: {
    'Content-Type': 'application/json',
  },
})

export default calibrationClient
