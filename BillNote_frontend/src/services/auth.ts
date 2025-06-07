import request from '@/utils/request'
import toast from 'react-hot-toast'

export interface QRCodeResponse {
  session_id: string
  qr_code: string  // base64格式的二维码图片
  expires_in: number
  message: string
}

export interface LoginStatusResponse {
  status: 'pending' | 'success' | 'failed' | 'expired'
  message: string
  cookie?: string
}

export interface CookieStatus {
  [platform: string]: {
    has_cookie: boolean
    cookie_preview: string
  }
}

/**
 * 生成登录二维码
 */
export const generateQRCode = async (platform: string): Promise<QRCodeResponse | null> => {
  try {
    console.log('📱 生成二维码请求:', platform)
    const response = await request.post('/auth/generate_qr', { platform })
    
    if (response.data.code === 0) {
      console.log('✅ 二维码生成成功')
      return response.data.data
    } else {
      console.error('❌ 二维码生成失败:', response.data.message)
      toast.error(response.data.message || '二维码生成失败')
      return null
    }
  } catch (e) {
    console.error('❌ 二维码生成请求异常:', e)
    toast.error('二维码生成失败，请稍后重试')
    return null
  }
}

/**
 * 检查登录状态
 */
export const checkLoginStatus = async (sessionId: string): Promise<LoginStatusResponse | null> => {
  try {
    const response = await request.get(`/auth/login_status/${sessionId}`)
    
    if (response.data.code === 0) {
      return response.data.data
    } else {
      console.error('❌ 登录状态检查失败:', response.data.message)
      return null
    }
  } catch (e) {
    console.error('❌ 登录状态检查异常:', e)
    return null
  }
}

/**
 * 获取cookie状态
 */
export const getCookieStatus = async (): Promise<CookieStatus | null> => {
  try {
    const response = await request.get('/auth/cookie_status')
    
    if (response.data.code === 0) {
      return response.data.data
    } else {
      console.error('❌ 获取cookie状态失败:', response.data.message)
      return null
    }
  } catch (e) {
    console.error('❌ 获取cookie状态异常:', e)
    return null
  }
}

/**
 * 清除平台cookie
 */
export const clearPlatformCookie = async (platform: string): Promise<boolean> => {
  try {
    const response = await request.delete(`/auth/clear_cookie/${platform}`)
    
    if (response.data.code === 0) {
      toast.success(`已清除${platform}的登录信息`)
      return true
    } else {
      console.error('❌ 清除cookie失败:', response.data.message)
      toast.error(response.data.message || '清除失败')
      return false
    }
  } catch (e) {
    console.error('❌ 清除cookie异常:', e)
    toast.error('清除失败，请稍后重试')
    return false
  }
} 