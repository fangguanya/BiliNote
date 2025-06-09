import axios from 'axios'

// 动态获取API基础URL - 临时修复：强制使用直接连接
const getApiBaseUrl = () => {
  // 强制使用直接连接到后端，避免代理问题
  return 'http://localhost:8000/api'
  
  // 原来的逻辑保留，等代理问题解决后可以恢复
  // if (import.meta.env.DEV) {
  //   return '/api'
  // }
  // return import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
}

const request = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 30000, // 增加超时时间以适应迁移操作
})

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    console.log(`🌐 API请求: ${config.method?.toUpperCase()} ${config.baseURL}${config.url}`)
    return config
  },
  (error) => {
    console.error('❌ 请求拦截器错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  (response) => {
    console.log(`✅ API响应: ${response.config.method?.toUpperCase()} ${response.config.url} - ${response.status}`)
    return response
  },
  (error) => {
    console.error('❌ API错误:', error)
    console.error('❌ 错误详情:', {
      url: error.config?.url,
      method: error.config?.method,
      baseURL: error.config?.baseURL,
      status: error.response?.status,
      data: error.response?.data
    })
    return Promise.reject(error)
  }
)

function handleErrorResponse(response: any) {
  if (!response) return '请求失败，请检查网络连接'
  if (typeof response.code !== 'number') return '系统异常'

  // 错误码判断
  switch (response.code) {
    case 1001:
      return response.msg || '下载失败，请检查视频链接'
    case 1002:
      return response.msg || '转写失败，请稍后重试'
    case 1003:
      return response.msg || '总结失败，可能是模型服务异常'
    case 2001:
    case 2002:
      return Array.isArray(response.data)
        ? response.data.map((e: any) => `${e.field}: ${e.error}`).join('\n')
        : response.msg || '参数错误'
    default:
      return response.msg || '系统异常'
  }
}

export default request
