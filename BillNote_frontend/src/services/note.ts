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
