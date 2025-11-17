import axios from 'axios'

// API Service 客户端 - 连接到 FastAPI 后端 (8001端口)
const calibrationClient = axios.create({
  baseURL: 'http://localhost:8001/api/v1',
  timeout: 30000, // 校准操作可能需要更长时间
  headers: {
    'Content-Type': 'application/json',
  },
})

export default calibrationClient
