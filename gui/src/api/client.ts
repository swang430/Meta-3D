import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 1500,
})

export default client
