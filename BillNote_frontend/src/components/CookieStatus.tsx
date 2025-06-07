import React, { useState, useEffect } from 'react'
import { Shield, ShieldCheck, ShieldX, Trash2, LogIn } from 'lucide-react'
import { getCookieStatus, clearPlatformCookie, CookieStatus } from '@/services/auth'
import LoginModal from './LoginModal'
import toast from 'react-hot-toast'

const CookieStatusComponent: React.FC = () => {
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [selectedPlatform, setSelectedPlatform] = useState('')

  // 平台配置
  const platformConfig = {
    bilibili: {
      name: '哔哩哔哩',
      color: 'text-pink-500',
      bgColor: 'bg-pink-50',
      borderColor: 'border-pink-200'
    },
    douyin: {
      name: '抖音',
      color: 'text-black',
      bgColor: 'bg-gray-50',
      borderColor: 'border-gray-200'
    }
  }

  // 加载cookie状态
  const loadCookieStatus = async () => {
    try {
      setLoading(true)
      const status = await getCookieStatus()
      setCookieStatus(status)
    } catch (error) {
      console.error('获取cookie状态失败:', error)
      toast.error('获取登录状态失败')
    } finally {
      setLoading(false)
    }
  }

  // 清除cookie
  const handleClearCookie = async (platform: string) => {
    const success = await clearPlatformCookie(platform)
    if (success) {
      loadCookieStatus() // 重新加载状态
    }
  }

  // 开始登录
  const handleLogin = (platform: string) => {
    setSelectedPlatform(platform)
    setShowLoginModal(true)
  }

  // 登录成功
  const handleLoginSuccess = () => {
    loadCookieStatus() // 重新加载状态
  }

  // 组件挂载时加载状态
  useEffect(() => {
    loadCookieStatus()
  }, [])

  if (loading) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-gray-400" />
          <span className="text-sm text-gray-600">加载登录状态...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center gap-2">
        <Shield className="h-5 w-5 text-gray-600" />
        <h3 className="font-medium text-gray-900">平台登录状态</h3>
      </div>

      <div className="space-y-3">
        {Object.entries(platformConfig).map(([platform, config]) => {
          const status = cookieStatus?.[platform]
          const hasLogin = status?.has_cookie

          return (
            <div
              key={platform}
              className={`flex items-center justify-between rounded-lg border p-3 ${config.bgColor} ${config.borderColor}`}
            >
              <div className="flex items-center gap-3">
                {hasLogin ? (
                  <ShieldCheck className={`h-5 w-5 text-green-500`} />
                ) : (
                  <ShieldX className={`h-5 w-5 text-gray-400`} />
                )}
                
                <div>
                  <div className="font-medium text-gray-900">{config.name}</div>
                  <div className="text-xs text-gray-500">
                    {hasLogin ? '已登录' : '未登录'}
                    {hasLogin && status?.cookie_preview && (
                      <span className="ml-2 font-mono">
                        {status.cookie_preview}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex gap-2">
                {hasLogin ? (
                  <button
                    onClick={() => handleClearCookie(platform)}
                    className="flex items-center gap-1 rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                  >
                    <Trash2 className="h-3 w-3" />
                    清除
                  </button>
                ) : (
                  <button
                    onClick={() => handleLogin(platform)}
                    className={`flex items-center gap-1 rounded px-2 py-1 text-xs text-white hover:opacity-90 ${
                      platform === 'bilibili' ? 'bg-pink-500' : 'bg-gray-900'
                    }`}
                  >
                    <LogIn className="h-3 w-3" />
                    登录
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="mt-3 rounded-lg bg-blue-50 p-3">
        <p className="text-xs text-blue-800">
          💡 登录后可以下载需要会员权限的视频和音频，提升下载成功率
        </p>
      </div>

      {/* 登录弹窗 */}
      <LoginModal
        isOpen={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        platform={selectedPlatform}
        onLoginSuccess={handleLoginSuccess}
      />
    </div>
  )
}

export default CookieStatusComponent 