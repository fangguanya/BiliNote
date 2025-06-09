import axios from 'axios'
import type { Task } from '@/store/taskStore'

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

const API_BASE = getApiBaseUrl()

export interface TaskCreate {
  id: string
  platform: string
  formData: any
}

export interface TaskUpdate {
  status?: string
  markdown?: string | any[]
  transcript?: any
  audioMeta?: any
  notion?: any
}

export interface TaskResponse {
  tasks: Task[]
  total: number
  currentTaskId?: string
}

/**
 * 转换前端Task数据格式为后端兼容格式
 */
const convertTaskForBackend = (task: Task) => {
  // 确保duration字段是数字类型
  const audioMeta = task.audioMeta || {}
  let duration = audioMeta.duration
  
  // 处理duration字段的类型转换
  if (typeof duration === 'string') {
    duration = parseInt(duration) || 0
  } else if (typeof duration !== 'number' || isNaN(duration)) {
    duration = 0
  } else {
    // 确保是整数
    duration = Math.floor(Number(duration))
  }

  const convertedTask = {
    id: task.id,
    markdown: task.markdown || "",
    transcript: task.transcript || {
      full_text: "",
      language: "",
      raw: null,
      segments: []
    },
    status: task.status || "PENDING",
    audioMeta: {
      cover_url: audioMeta.cover_url || "",
      duration: duration, // 确保是数字类型
      file_path: audioMeta.file_path || "",
      platform: audioMeta.platform || "",
      raw_info: audioMeta.raw_info || null,
      title: audioMeta.title || "",
      video_id: audioMeta.video_id || ""
    },
    createdAt: task.createdAt,
    platform: task.platform,
    notion: task.notion || null,
    formData: {
      video_url: task.formData.video_url,
      link: task.formData.link === undefined ? null : task.formData.link,
      screenshot: task.formData.screenshot === undefined ? null : task.formData.screenshot,
      platform: task.formData.platform,
      quality: task.formData.quality || "high",
      model_name: task.formData.model_name,
      provider_id: task.formData.provider_id,
      style: task.formData.style || null,
      format: task.formData.format || null,
      extras: task.formData.extras || null,
      video_understanding: task.formData.video_understanding === undefined ? false : task.formData.video_understanding,
      video_interval: task.formData.video_interval || null,
      grid_size: task.formData.grid_size || null,
      max_collection_videos: task.formData.max_collection_videos || null,
      auto_save_notion: task.formData.auto_save_notion === undefined ? false : task.formData.auto_save_notion
    }
  }

  // 记录包含文件数据的任务信息
  if (audioMeta.cover_url || audioMeta.file_path || audioMeta.title) {
    console.log(`📁 任务 ${task.id} 包含文件数据:`, {
      cover_url: audioMeta.cover_url ? '✅' : '❌',
      file_path: audioMeta.file_path ? '✅' : '❌', 
      title: audioMeta.title ? '✅' : '❌',
      duration: duration > 0 ? '✅' : '❌'
    })
  }

  // 检查markdown内容是否包含图片
  if (typeof task.markdown === 'string' && task.markdown.includes('![')) {
    console.log(`🖼️ 任务 ${task.id} 的markdown包含图片`)
  } else if (Array.isArray(task.markdown)) {
    const hasImages = task.markdown.some(md => md.content.includes('!['))
    if (hasImages) {
      console.log(`🖼️ 任务 ${task.id} 的markdown版本包含图片`)
    }
  }

  return convertedTask
}

/**
 * 创建新任务
 */
export const createTask = async (task: TaskCreate) => {
  const response = await axios.post(`${API_BASE}/tasks`, task)
  return response.data
}

/**
 * 获取任务列表
 */
export const getTasks = async (params?: {
  limit?: number
  offset?: number
  status?: string
}): Promise<TaskResponse> => {
  const response = await axios.get(`${API_BASE}/tasks`, { params })
  return response.data
}

/**
 * 根据ID获取单个任务
 */
export const getTask = async (taskId: string): Promise<Task> => {
  const response = await axios.get(`${API_BASE}/tasks/${taskId}`)
  return response.data
}

/**
 * 更新任务
 */
export const updateTask = async (taskId: string, updateData: TaskUpdate) => {
  const response = await axios.put(`${API_BASE}/tasks/${taskId}`, updateData)
  return response.data
}

/**
 * 删除任务
 */
export const deleteTask = async (taskId: string) => {
  const response = await axios.delete(`${API_BASE}/tasks/${taskId}`)
  return response.data
}

/**
 * 批量创建任务
 */
export const createBatchTasks = async (tasks: TaskCreate[]) => {
  const response = await axios.post(`${API_BASE}/tasks/batch`, tasks)
  return response.data
}

/**
 * 根据状态获取任务
 */
export const getTasksByStatus = async (status: string): Promise<Task[]> => {
  const response = await axios.get(`${API_BASE}/tasks/status/${status}`)
  return response.data
}

/**
 * 从前端迁移任务到后端
 */
export const migrateTasks = async (tasks: Task[]) => {
  console.log(`🔄 尝试迁移 ${tasks.length} 个任务到: ${API_BASE}/tasks/migrate`)
  console.log('📝 迁移数据示例（前3个任务）:', tasks.slice(0, 3))
  
  // 转换数据格式
  const convertedTasks = tasks.map(convertTaskForBackend)
  console.log('🔄 转换后的数据示例（前3个任务）:', convertedTasks.slice(0, 3))
  
  // 检查转换后的audioMeta.duration字段
  const durationSample = convertedTasks.slice(0, 5).map(task => ({
    id: task.id,
    duration: task.audioMeta.duration,
    durationType: typeof task.audioMeta.duration
  }))
  console.log('🔍 Duration字段检查:', durationSample)
  
  // 统计文件数据
  const fileDataStats = {
    tasksWithCover: 0,
    tasksWithAudio: 0,
    tasksWithImages: 0,
    tasksWithTitle: 0,
    totalFiles: 0
  }
  
  convertedTasks.forEach(task => {
    if (task.audioMeta.cover_url) {
      fileDataStats.tasksWithCover++
      fileDataStats.totalFiles++
    }
    if (task.audioMeta.file_path) {
      fileDataStats.tasksWithAudio++
      fileDataStats.totalFiles++
    }
    if (task.audioMeta.title) {
      fileDataStats.tasksWithTitle++
    }
    
    // 检查markdown中的图片
    if (typeof task.markdown === 'string' && task.markdown.includes('![')) {
      fileDataStats.tasksWithImages++
    } else if (Array.isArray(task.markdown)) {
      const hasImages = task.markdown.some(md => md.content.includes('!['))
      if (hasImages) {
        fileDataStats.tasksWithImages++
      }
    }
  })
  
  console.log('📊 文件数据统计:', fileDataStats)
  
  try {
    const response = await axios.post(`${API_BASE}/tasks/migrate`, convertedTasks, {
      headers: {
        'Content-Type': 'application/json'
      },
      timeout: 60000 // 增加超时时间
    })
    
    console.log('✅ 迁移成功响应:', response.data)
    
    // 验证迁移结果中的文件数据保留情况
    if (response.data.migrated_count > 0 || response.data.total_count > 0) {
      console.log(`📁 文件数据迁移确认: ${fileDataStats.totalFiles} 个文件引用已迁移`)
      if (fileDataStats.tasksWithCover > 0) {
        console.log(`🖼️ ${fileDataStats.tasksWithCover} 个任务包含封面图片`)
      }
      if (fileDataStats.tasksWithAudio > 0) {
        console.log(`🎵 ${fileDataStats.tasksWithAudio} 个任务包含音频文件`)
      }
      if (fileDataStats.tasksWithImages > 0) {
        console.log(`🖼️ ${fileDataStats.tasksWithImages} 个任务的markdown包含图片`)
      }
    }
    
    return response.data
  } catch (error: any) {
    console.error('❌ 迁移请求失败:', error)
    console.error('❌ 错误响应数据:', error.response?.data)
    console.error('❌ 错误状态码:', error.response?.status)
    console.error('❌ 错误头部:', error.response?.headers)
    
    // 详细展示验证错误
    if (error.response?.data?.data && Array.isArray(error.response.data.data)) {
      console.error('🔍 详细验证错误（前10个）:', error.response.data.data.slice(0, 10))
      console.error('📊 验证错误总数:', error.response.data.data.length)
      
      // 分析错误模式
      const errorTypes = error.response.data.data.reduce((acc: any, err: any) => {
        const key = err.field || err.loc?.join('.') || 'unknown'
        acc[key] = (acc[key] || 0) + 1
        return acc
      }, {})
      console.error('📈 错误字段统计:', errorTypes)
    }
    
    throw error
  }
}

export const validateFilesIntegrity = async () => {
  try {
    console.log('🔍 开始验证文件数据完整性...')
    const response = await axios.get(`${API_BASE}/tasks/validate-files`, {
      timeout: 30000
    })
    
    const stats = response.data.statistics
    console.log('✅ 文件完整性验证结果:', stats)
    
    // 详细输出统计信息
    console.log(`📊 总任务数: ${stats.total_tasks}`)
    console.log(`🖼️ 包含封面图片的任务: ${stats.tasks_with_cover}`)
    console.log(`🎵 包含音频文件的任务: ${stats.tasks_with_audio}`) 
    console.log(`📝 包含标题的任务: ${stats.tasks_with_title}`)
    console.log(`🖼️ Markdown包含图片的任务: ${stats.tasks_with_images}`)
    
    if (stats.file_references && stats.file_references.length > 0) {
      console.log(`📁 包含文件引用的任务详情 (${stats.file_references.length}个):`)
      stats.file_references.slice(0, 10).forEach((ref: any) => {
        console.log(`  - 任务 ${ref.task_id}:`, {
          封面: ref.cover_url ? '✅' : '❌',
          音频: ref.file_path ? '✅' : '❌',
          标题: ref.title ? '✅' : '❌',
          图片: ref.has_images ? '✅' : '❌'
        })
      })
      
      if (stats.file_references.length > 10) {
        console.log(`  ... 还有 ${stats.file_references.length - 10} 个任务`)
      }
    }
    
    return response.data
  } catch (error: any) {
    console.error('❌ 文件完整性验证失败:', error)
    throw error
  }
} 