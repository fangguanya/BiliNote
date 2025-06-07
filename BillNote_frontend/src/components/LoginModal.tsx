import React, { useState, useEffect, useRef } from 'react'
import { X, RefreshCw, CheckCircle, XCircle, Clock, Smartphone } from 'lucide-react'
import { generateQRCode, checkLoginStatus, QRCodeResponse, LoginStatusResponse } from '@/services/auth'
import toast from 'react-hot-toast'

interface LoginModalProps {
  isOpen: boolean
  onClose: () => void
  platform: string
  onLoginSuccess: () => void
}

type LoginStatus = 'pending' | 'success' | 'failed' | 'expired' | 'loading'

const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose, platform, onLoginSuccess }) => {
  const [qrData, setQrData] = useState<QRCodeResponse | null>(null)
  const [status, setStatus] = useState<LoginStatus>('loading')
  const [message, setMessage] = useState('')
  const [timeLeft, setTimeLeft] = useState(0)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)
  const timerRef = useRef<NodeJS.Timeout | null>(null)

  // 平台信息配置
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
    },
    kuaishou: {
      name: '快手',
      color: 'text-orange-500',
      bgColor: 'bg-orange-50',
      borderColor: 'border-orange-200'
    }
  }

  const config = platformConfig[platform as keyof typeof platformConfig] || platformConfig.bilibili

  // 生成二维码
  const generateQR = async () => {
    setStatus('loading')
    setMessage('正在生成二维码...')
    
    try {
      const response = await generateQRCode(platform)
      if (response) {
        setQrData(response)
        setStatus('pending')
        setMessage(response.message)
        setTimeLeft(response.expires_in)
        startPolling(response.session_id)
        startTimer()
      } else {
        setStatus('failed')
        setMessage('二维码生成失败')
      }
    } catch (error) {
      console.error('生成二维码失败:', error)
      setStatus('failed')
      setMessage('二维码生成失败')
    }
  }

  // 开始轮询登录状态
  const startPolling = (sessionId: string) => {
    stopPolling()
    
    pollingRef.current = setInterval(async () => {
      try {
        const response = await checkLoginStatus(sessionId)
        if (response) {
          setMessage(response.message)
          
          if (response.status === 'success') {
            setStatus('success')
            stopPolling()
            stopTimer()
            toast.success('登录成功！')
            setTimeout(() => {
              onLoginSuccess()
              onClose()
            }, 1500)
          } else if (response.status === 'failed') {
            setStatus('failed')
            stopPolling()
            stopTimer()
          } else if (response.status === 'expired') {
            setStatus('expired')
            stopPolling()
            stopTimer()
          }
          // pending状态继续轮询
        }
      } catch (error) {
        console.error('检查登录状态失败:', error)
      }
    }, 2000) // 每2秒检查一次
  }

  // 停止轮询
  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }

  // 开始倒计时
  const startTimer = () => {
    stopTimer()
    
    timerRef.current = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          setStatus('expired')
          setMessage('二维码已过期，请重新生成')
          stopPolling()
          stopTimer()
          return 0
        }
        return prev - 1
      })
    }, 1000)
  }

  // 停止倒计时
  const stopTimer = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  // 格式化剩余时间
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  // 重新生成二维码
  const handleRefresh = () => {
    stopPolling()
    stopTimer()
    generateQR()
  }

  // 关闭弹窗
  const handleClose = () => {
    stopPolling()
    stopTimer()
    onClose()
  }

  // 状态图标
  const getStatusIcon = () => {
    switch (status) {
      case 'loading':
        return <RefreshCw className="h-5 w-5 animate-spin text-blue-500" />
      case 'pending':
        return <Smartphone className={`h-5 w-5 ${config.color}`} />
      case 'success':
        return <CheckCircle className="h-5 w-5 text-green-500" />
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />
      case 'expired':
        return <Clock className="h-5 w-5 text-orange-500" />
      default:
        return null
    }
  }

  // 组件挂载时生成二维码
  useEffect(() => {
    if (isOpen) {
      generateQR()
    } else {
      stopPolling()
      stopTimer()
    }
    
    return () => {
      stopPolling()
      stopTimer()
    }
  }, [isOpen, platform])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 backdrop-blur-sm">
      <div className="relative w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        {/* 关闭按钮 */}
        <button
          onClick={handleClose}
          className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
        >
          <X className="h-5 w-5" />
        </button>

        {/* 头部 */}
        <div className="mb-6 text-center">
          <h2 className="text-xl font-semibold text-gray-900">
            {config.name}登录
          </h2>
          <p className="mt-2 text-sm text-gray-600">
            使用{config.name}APP扫描二维码登录
          </p>
        </div>

        {/* 二维码区域 */}
        <div className={`mb-6 flex flex-col items-center rounded-lg ${config.bgColor} ${config.borderColor} border p-6`}>
          {status === 'loading' ? (
            <div className="flex h-48 w-48 items-center justify-center">
              <RefreshCw className="h-8 w-8 animate-spin text-gray-400" />
            </div>
          ) : qrData ? (
            <div className="relative">
              <img
                src={qrData.qr_code}
                alt="登录二维码"
                className="h-48 w-48 rounded-lg"
              />
              {(status === 'expired' || status === 'failed') && (
                <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-black bg-opacity-50">
                  <button
                    onClick={handleRefresh}
                    className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50"
                  >
                    <RefreshCw className="h-4 w-4" />
                    重新生成
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="flex h-48 w-48 items-center justify-center text-gray-400">
              二维码生成失败
            </div>
          )}
        </div>

        {/* 状态信息 */}
        <div className="mb-4 text-center">
          <div className="mb-2 flex items-center justify-center gap-2">
            {getStatusIcon()}
            <span className="text-sm font-medium text-gray-900">{message}</span>
          </div>
          
          {status === 'pending' && timeLeft > 0 && (
            <div className="text-xs text-gray-500">
              二维码有效期：{formatTime(timeLeft)}
            </div>
          )}
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-3">
          <button
            onClick={handleClose}
            className="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            取消
          </button>
          
          {(status === 'expired' || status === 'failed') && (
            <button
              onClick={handleRefresh}
              className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium text-white hover:opacity-90 ${
                platform === 'bilibili' ? 'bg-pink-500' : 
                platform === 'douyin' ? 'bg-gray-900' :
                platform === 'kuaishou' ? 'bg-orange-500' : 'bg-gray-900'
              }`}
            >
              重新生成
            </button>
          )}
        </div>

        {/* 提示信息 */}
        <div className="mt-4 rounded-lg bg-blue-50 p-3">
          <p className="text-xs text-blue-800">
            💡 登录后可以下载需要会员权限的视频和音频
          </p>
        </div>
      </div>
    </div>
  )
}

export default LoginModal 