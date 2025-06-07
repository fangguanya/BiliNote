// 下载器登录设置页面（自动获取Cookie）
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { LogIn, Shield, ShieldCheck, ShieldX, Trash2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import toast from 'react-hot-toast'
import { getDownloaderCookie } from '@/services/downloader'
import { getCookieStatus, clearPlatformCookie } from '@/services/auth'
import { videoPlatforms } from '@/constant/note.ts'
import LoginModal from '@/components/LoginModal'

const DownloaderForm = () => {
  const { id } = useParams()
  const [loading, setLoading] = useState(true)
  const [cookieExists, setCookieExists] = useState(false)
  const [cookiePreview, setCookiePreview] = useState('')
  const [showLoginModal, setShowLoginModal] = useState(false)

  const platformInfo = videoPlatforms.find(item => item.value === id)

  // 平台配置
  const platformConfig = {
    bilibili: {
      name: '哔哩哔哩',
      color: 'text-pink-500',
      bgColor: 'bg-pink-50',
      borderColor: 'border-pink-200',
      icon: '📺'
    },
    douyin: {
      name: '抖音',
      color: 'text-black',
      bgColor: 'bg-gray-50',
      borderColor: 'border-gray-200',
      icon: '🎵'
    },
    kuaishou: {
      name: '快手',
      color: 'text-orange-500',
      bgColor: 'bg-orange-50',
      borderColor: 'border-orange-200',
      icon: '⚡'
    }
  }

  const config = platformConfig[id as keyof typeof platformConfig] || platformConfig.bilibili

  const loadCookieStatus = async () => {
    setLoading(true)
    try {
      // 检查cookie状态
      const cookieStatus = await getCookieStatus()
      
      if (cookieStatus && id) {
        const platformStatus = cookieStatus[id]
        
        if (platformStatus) {
          setCookieExists(platformStatus.has_cookie)
          setCookiePreview(platformStatus.cookie_preview || '')
        } else {
          setCookieExists(false)
          setCookiePreview('')
        }
      } else {
        setCookieExists(false)
        setCookiePreview('')
      }
    } catch (e) {
      console.error('加载Cookie状态失败:', e)
      toast.error('加载登录状态失败')
    } finally {
      setLoading(false)
    }
  }

  const handleLogin = () => {
    setShowLoginModal(true)
  }

  const handleLoginSuccess = () => {
    loadCookieStatus() // 重新加载状态
  }

  const handleClearCookie = async () => {
    if (!id) {
      toast.error('无效的平台参数')
      return
    }
    
    const success = await clearPlatformCookie(id)
    if (success) {
      loadCookieStatus() // 重新加载状态
    }
  }

  useEffect(() => {
    if (id) {
      loadCookieStatus()
    }
  }, [id])

  if (loading) {
    return (
      <div className="max-w-xl p-4">
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="h-6 w-6 animate-spin text-gray-400" />
          <span className="ml-2 text-gray-600">加载中...</span>
        </div>
      </div>
    )
  }

  // 如果没有id参数，显示错误信息
  if (!id) {
    return (
      <div className="max-w-xl p-4">
        <Card className="border-red-200 border">
          <CardContent className="pt-6">
            <div className="text-center">
              <p className="text-red-600">无效的平台参数</p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="max-w-xl p-4">
      <Card className={`${config.borderColor} border`}>
        <CardHeader className={config.bgColor}>
          <CardTitle className="flex items-center gap-3">
            <span className="text-2xl">{config.icon}</span>
            <div>
              <h2 className={`text-xl font-bold ${config.color}`}>
                {config.name}登录设置
              </h2>
              <CardDescription>
                扫码登录自动获取Cookie，提升下载体验
              </CardDescription>
            </div>
          </CardTitle>
        </CardHeader>
        
        <CardContent className="pt-6">
          {/* 登录状态显示 */}
          <div className="mb-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {cookieExists ? (
                  <>
                    <ShieldCheck className="h-5 w-5 text-green-500" />
                    <span className="font-medium text-green-700">已登录</span>
                    <Badge variant="outline" className="text-green-600 border-green-300">
                      活跃
                    </Badge>
                  </>
                ) : (
                  <>
                    <ShieldX className="h-5 w-5 text-gray-400" />
                    <span className="font-medium text-gray-600">未登录</span>
                    <Badge variant="outline" className="text-gray-500">
                      需要登录
                    </Badge>
                  </>
                )}
              </div>
              
              {cookieExists && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleClearCookie}
                  className="text-red-600 hover:text-red-700 hover:bg-red-50"
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  清除
                </Button>
              )}
            </div>
            
            {cookiePreview && (
              <div className="mt-2 p-2 bg-gray-50 rounded text-xs text-gray-600 font-mono">
                Cookie预览: {cookiePreview}
              </div>
            )}
          </div>
          
          {/* 操作按钮 */}
          <div className="space-y-4">
            <Button
              onClick={handleLogin}
              className={`w-full ${
                id === 'bilibili' ? 'bg-pink-500 hover:bg-pink-600' : 
                id === 'douyin' ? 'bg-gray-900 hover:bg-gray-800' :
                'bg-orange-500 hover:bg-orange-600'
              }`}
            >
              <LogIn className="h-4 w-4 mr-2" />
              {cookieExists ? '重新登录' : '扫码登录'}
            </Button>
            
            {/* 功能说明 */}
            <div className="p-4 bg-blue-50 rounded-lg">
              <h4 className="text-sm font-medium text-blue-900 mb-2">
                ✨ 登录后可享受以下功能：
              </h4>
              <ul className="text-xs text-blue-800 space-y-1">
                <li>• 下载需要会员权限的高清视频</li>
                <li>• 访问私密或登录才能查看的内容</li>
                <li>• 获得更稳定的下载体验</li>
                <li>• 避免频率限制和反爬措施</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 登录模态框 */}
      <LoginModal
        isOpen={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        platform={id}
        onLoginSuccess={handleLoginSuccess}
      />
    </div>
  )
}

export default DownloaderForm

