import request from '@/utils/request'
import toast from 'react-hot-toast'

// 认证错误接口
export interface AuthError {
  code: string
  platform: string
  msg: string
  error: string
}

// 检查是否为认证错误
export const isAuthError = (error: any): AuthError | null => {
  if (error.response?.status === 401 && error.response?.data?.detail?.code === 'AUTH_REQUIRED') {
    return error.response.data.detail as AuthError
  }
  return null
}

export const generateNote = async (data: {
  video_url: string
  platform: string
  quality: string
  model_name: string
  provider_id: string
  task_id?: string
  format: Array<string>
  style: string
  extras?: string
  video_understanding?: boolean
  video_interval?: number
  grid_size:Array<number>
  max_collection_videos?: number
}) => {
  try {
    console.log('📡 发送请求到后端:', data)
    const response = await request.post('/generate_note', data)
    console.log('📥 收到后端响应:', response)

    // 检查后端响应格式 (新的StandardResponse格式)
    if (!response.data.success) {
      const errorMsg = response.data.message || '请求失败'
      console.error('❌ 后端返回错误:', errorMsg)
      toast.error(errorMsg)
      return null
    }

    const responseData = response.data.data
    console.log('📊 解析响应数据:', responseData)

    // 检查是否为合集响应
    if (responseData?.is_collection) {
      // 合集处理
      const { total_videos, created_tasks, task_list, message } = responseData
      console.log('🎬 处理合集响应:', { total_videos, created_tasks, task_list })
      
      toast.success(message || `已成功为合集中的 ${created_tasks} 个视频创建任务，视频数量 ${total_videos}！`)
      
      // 返回合集信息，让调用方处理批量添加任务
      return {
        success: true,
        isCollection: true,
        taskList: task_list,
        totalVideos: total_videos,
        createdTasks: created_tasks,
        message: message
      }
    } else {
      // 单个视频处理
      console.log('📺 处理单视频响应:', responseData)
      toast.success('笔记生成任务已提交！')
      return {
        success: true,
        isCollection: false,
        data: responseData
      }
    }
  } catch (e: any) {
    console.error('❌ 请求出错', e)
    
    // 检查是否为认证错误
    const authError = isAuthError(e)
    if (authError) {
      console.log('🔐 检测到认证错误:', authError)
      // 不显示错误toast，让调用方处理登录弹窗
      throw { type: 'AUTH_REQUIRED', authError }
    }
    
    if (e.response?.data?.message) {
      toast.error(e.response.data.message)
    } else {
      toast.error('笔记生成失败，请稍后重试')
    }
    throw e // 抛出错误以便调用方处理
  }
}

export const delete_task = async ({ video_id, platform }: { video_id: string, platform: string }) => {
  try {
    const data = {
      video_id,
      platform,
    }
    const res = await request.post('/delete_task', data)

    if (res.data.code === 0) {
      toast.success('任务已成功删除')
      return res.data
    } else {
      toast.error(res.data.message || '删除失败')
      throw new Error(res.data.message || '删除失败')
    }
  } catch (e) {
    toast.error('请求异常，删除任务失败')
    console.error('❌ 删除任务失败:', e)
    throw e
  }
}

export const get_task_status = async (task_id: string) => {
  try {
    const response = await request.get('/task_status/' + task_id)

    if (response.data.code == 0 && response.data.status == 'SUCCESS') {
      // toast.success("笔记生成成功")
    }
    console.log('res', response)
    // 成功提示

    return response.data
  } catch (e) {
    console.error('❌ 请求出错', e)

    // 错误提示
    toast.error('笔记生成失败，请稍后重试')

    throw e // 抛出错误以便调用方处理
  }
}

export const retry_task = async (task_id: string) => {
  try {
    const response = await request.post(`/retry_task/${task_id}`)
    
    if (response.data.code === 0) {
      toast.success('任务重试成功，请等待处理')
      return response.data
    } else {
      toast.error(response.data.message || '重试失败')
      throw new Error(response.data.message || '重试失败')
    }
  } catch (e: any) {
    console.error('❌ 重试任务失败:', e)
    toast.error('重试任务失败，请稍后重试')
    throw e
  }
}

// 批量重试失败任务
export const batch_retry_failed_tasks = async () => {
  try {
    const response = await request.post('/batch_retry_failed')
    
    if (response.data.code === 0) {
      const result = response.data.data
      if (result.retried_count > 0) {
        toast.success(`成功重试 ${result.retried_count} 个失败任务`)
      } else {
        toast('没有需要重试的失败任务')
      }
      return result
    } else {
      toast.error(response.data.message || '批量重试失败')
      throw new Error(response.data.message || '批量重试失败')
    }
  } catch (e: any) {
    console.error('❌ 批量重试失败任务出错:', e)
    toast.error('批量重试失败，请稍后重试')
    throw e
  }
}

// 批量重试所有非成功任务
export const batch_retry_non_success_tasks = async () => {
  try {
    const response = await request.post('/batch_retry_non_success')
    
    if (response.data.code === 0) {
      const result = response.data.data
      if (result.retried_count > 0) {
        const statusInfo = `PENDING:${result.pending_count}, RUNNING:${result.running_count}, FAILED:${result.failed_count}`
        toast.success(`成功重试 ${result.retried_count} 个非成功任务 (${statusInfo})`)
      } else {
        toast('没有需要重试的非成功任务')
      }
      return result
    } else {
      toast.error(response.data.message || '批量重试非成功任务失败')
      throw new Error(response.data.message || '批量重试非成功任务失败')
    }
  } catch (e: any) {
    console.error('❌ 批量重试非成功任务出错:', e)
    toast.error('批量重试非成功任务失败，请稍后重试')
    throw e
  }
}

// 强制重试所有任务
export const force_retry_all_tasks = async (task_ids: string[], config?: {
  model_name?: string
  provider_id?: string
  style?: string
  video_understanding?: boolean
  video_interval?: number
}) => {
  try {
    const payload = {
      task_ids: task_ids,
      config: config || {}
    }
    const response = await request.post('/force_retry_all', payload)
    if (response.data.success) {
      return response.data.data
    } else {
      toast.error(response.data.message || '强制重试失败')
      throw new Error(response.data.message || '强制重试失败')
    }
  } catch (e: any) {
    console.error('❌ 强制重试所有任务出错:', e)
    toast.error('强制重试失败，请稍后重试')
    throw e
  }
}

// 强制重试单个任务
export const force_retry_task = async (task_id: string) => {
  try {
    const response = await request.post(`/force_retry_task/${task_id}`, {})
    
    if (response.data.code === 0) {
      toast.success('任务强制重试成功，请等待处理')
      return response.data
    } else {
      toast.error(response.data.message || '强制重试失败')
      throw new Error(response.data.message || '强制重试失败')
    }
  } catch (e: any) {
    console.error('❌ 强制重试任务失败:', e)
    toast.error('强制重试任务失败，请稍后重试')
    throw e
  }
}

// 强制重启任务 - 完全清理并重新开始
export const force_restart_task = async (task_id: string) => {
  try {
    const response = await request.post(`/force_restart_task/${task_id}`)
    
    if (response.data.code === 0) {
      const result = response.data.data
      toast.success(`任务强制重启成功: ${result.title || '未知标题'}`)
      return response.data
    } else {
      toast.error(response.data.message || '强制重启失败')
      throw new Error(response.data.message || '强制重启失败')
    }
  } catch (e: any) {
    console.error('❌ 强制重启任务失败:', e)
    toast.error('强制重启任务失败，请稍后重试')
    throw e
  }
}

// 验证任务状态
export const validate_tasks = async (task_ids: string[]) => {
  try {
    const response = await request.post('/validate_tasks', { task_ids })
    
    if (response.data.code === 0) {
      const result = response.data.data
      console.log(`✅ 任务验证完成: ${result.message}`)
      return result
    } else {
      console.error('❌ 任务验证失败:', response.data.message)
      throw new Error(response.data.message || '任务验证失败')
    }
  } catch (e: any) {
    console.error('❌ 验证任务状态出错:', e)
    throw e
  }
}

// 清空重置单个任务
export const clear_reset_task = async (task_id: string) => {
  try {
    const response = await request.post(`/clear_reset_task/${task_id}`)
    
    if (response.data.code === 0) {
      toast.success('任务已清空重置，重新进入队列')
      return response.data
    } else {
      toast.error(response.data.message || '清空重置失败')
      throw new Error(response.data.message || '清空重置失败')
    }
  } catch (e: any) {
    console.error('❌ 清空重置任务失败:', e)
    toast.error('清空重置任务失败，请稍后重试')
    throw e
  }
}

// 批量清空重置任务
export const batch_clear_reset_tasks = async (task_ids: string[], force_clear: boolean = false) => {
  try {
    const response = await request.post('/batch_clear_reset_tasks', { 
      task_ids, 
      force_clear 
    })
    
    if (response.data.code === 0) {
      const result = response.data.data
      toast.success(result.message)
      return result
    } else {
      toast.error(response.data.message || '批量清空重置失败')
      throw new Error(response.data.message || '批量清空重置失败')
    }
  } catch (e: any) {
    console.error('❌ 批量清空重置任务失败:', e)
    toast.error('批量清空重置任务失败，请稍后重试')
    throw e
  }
}

// 百度网盘相关API

// 获取百度网盘认证状态
export const getBaiduPanAuthStatus = async () => {
  try {
    const response = await request.get('/baidu_pan/auth_status')
    return response.data
  } catch (e: any) {
    console.error('❌ 获取百度网盘认证状态失败:', e)
    throw e
  }
}

// 获取百度网盘文件列表
export const getBaiduPanFileList = async (path: string = "/", shareCode?: string, extractCode?: string) => {
  try {
    const params: any = { path }
    if (shareCode) params.share_code = shareCode
    if (extractCode) params.extract_code = extractCode
    
    const response = await request.get('/baidu_pan/file_list', { params })
    
    if (response.data.code === 0) {
      return response.data.data
    } else {
      toast.error(response.data.message || '获取文件列表失败')
      throw new Error(response.data.message || '获取文件列表失败')
    }
  } catch (e: any) {
    console.error('❌ 获取百度网盘文件列表失败:', e)
    toast.error('获取文件列表失败，请稍后重试')
    throw e
  }
}

// 选择百度网盘文件并创建任务
export const selectBaiduPanFiles = async (selectedFiles: any[], taskConfig: any) => {
  try {
    const data = {
      selected_files: selectedFiles,
      task_config: taskConfig
    }
    
    const response = await request.post('/baidu_pan/select_files', data)
    
    if (response.data.code === 0) {
      const result = response.data.data
      toast.success(result.message || `已成功为 ${result.total_tasks} 个文件创建任务`)
      return result
    } else {
      toast.error(response.data.message || '选择文件失败')
      throw new Error(response.data.message || '选择文件失败')
    }
  } catch (e: any) {
    console.error('❌ 选择百度网盘文件失败:', e)
    toast.error('选择文件失败，请稍后重试')
    throw e
  }
}
