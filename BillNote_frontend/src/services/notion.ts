import request from '@/utils/request'
import { toast } from 'sonner'

export interface NotionDatabase {
  id: string
  title: string
  url: string
  created_time: string
  last_edited_time: string
}

export interface NotionConnectionResult {
  connected: boolean
  message: string
}

export interface NotionDatabaseListResult {
  databases: NotionDatabase[]
  count: number
}

export interface SaveToNotionResult {
  page_id: string
  url: string
  title: string
  message: string
}

/**
 * 测试Notion连接
 */
export const testNotionConnection = async (token: string): Promise<NotionConnectionResult | null> => {
  try {
    console.log('🔗 测试Notion连接...')
    console.log('📤 发送请求到:', '/notion/test_connection')
    console.log('📤 请求数据:', { token: token?.substring(0, 10) + '...' })
    
    const response = await request.post('/notion/test_connection', { token })
    console.log('📥 收到响应:', response)
    
    if (response.data.code === 0) {
      const result: NotionConnectionResult = response.data.data
      console.log('✅ Notion连接测试成功:', result)
      toast.success(result.message)
      return result
    } else {
      console.error('❌ Notion连接测试失败:', response.data.msg)
      toast.error(response.data.msg || '连接失败')
      return null
    }
  } catch (error: any) {
    console.error('❌ Notion连接测试失败:', error)
    console.error('❌ 错误详情:', {
      message: error.message,
      response: error.response?.data,
      status: error.response?.status,
      config: error.config
    })
    
    const errorMsg = error.response?.data?.msg || 
                    error.response?.data?.message || 
                    error.message || 
                    '连接测试失败，请检查网络和服务器状态'
    toast.error(errorMsg)
    return null
  }
}

/**
 * 获取Notion数据库列表
 */
export const getNotionDatabases = async (token: string): Promise<NotionDatabase[]> => {
  try {
    console.log('📊 获取Notion数据库列表...')
    const response = await request.post('/notion/list_databases', { token })
    
    if (response.data.code === 0) {
      const result: NotionDatabaseListResult = response.data.data
      console.log('✅ 成功获取数据库列表:', result)
      return result.databases
    } else {
      console.error('❌ 获取数据库列表失败:', response.data.msg)
      toast.error(response.data.msg)
      return []
    }
  } catch (error: any) {
    console.error('❌ 获取数据库列表请求失败:', error)
    const errorMsg = error.response?.data?.msg || error.message || '获取数据库列表失败'
    toast.error(errorMsg)
    return []
  }
}

/**
 * 保存笔记到Notion
 */
export const saveNoteToNotion = async (params: {
  taskId: string
  token: string
  databaseId?: string
  parentPageId?: string
}): Promise<SaveToNotionResult | null> => {
  try {
    console.log('📝 保存笔记到Notion...', params)
    const response = await request.post('/notion/save_note', {
      task_id: params.taskId,
      token: params.token,
      database_id: params.databaseId,
      parent_page_id: params.parentPageId
    })
    
    if (response.data.code === 0) {
      const result: SaveToNotionResult = response.data.data
      console.log('✅ 笔记保存成功:', result)
      toast.success(result.message)
      return result
    } else {
      console.error('❌ 保存到Notion失败:', response.data.msg)
      toast.error(response.data.msg)
      return null
    }
  } catch (error: any) {
    console.error('❌ 保存到Notion请求失败:', error)
    const errorMsg = error.response?.data?.msg || error.message || '保存到Notion失败'
    toast.error(errorMsg)
    return null
  }
}

/**
 * 检查Notion服务健康状态
 */
export const checkNotionHealth = async (): Promise<boolean> => {
  try {
    console.log('🩺 检查Notion服务健康状态...')
    const response = await request.get('/notion/health')
    console.log('🩺 健康检查响应:', response)
    return response.data.code === 0
  } catch (error) {
    console.error('❌ Notion服务健康检查失败:', error)
    return false
  }
}

/**
 * 调试：测试基础API连接
 */
export const debugApiConnection = async (): Promise<void> => {
  try {
    console.log('🔍 开始调试API连接...')
    
    // 测试基础API
    console.log('📡 测试基础API连接...')
    const baseResponse = await request.get('/health')
    console.log('📡 基础API响应:', baseResponse)
    
    // 测试Notion健康检查
    console.log('🩺 测试Notion健康检查...')
    const healthResponse = await request.get('/notion/health')
    console.log('🩺 Notion健康检查响应:', healthResponse)
    
    console.log('✅ API连接调试完成')
  } catch (error: any) {
    console.error('❌ API连接调试失败:', error)
    console.error('❌ 错误详情:', {
      message: error.message,
      response: error.response?.data,
      status: error.response?.status,
      config: error.config
    })
  }
} 