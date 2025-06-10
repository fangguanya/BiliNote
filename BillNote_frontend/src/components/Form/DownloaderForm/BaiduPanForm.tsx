import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { BaiduPanLogo } from '@/components/Icons/platform'
import toast from 'react-hot-toast'
import { 
  CheckIcon, 
  XIcon, 
  AlertCircleIcon, 
  LoaderIcon,
  UserIcon,
  PlusIcon,
  TrashIcon,
  RefreshCwIcon
} from 'lucide-react'

interface BaiduPCSUser {
  user_id: number
  user_name: string
  quota_used: number
  quota_total: number
  quota_used_readable: string
  quota_total_readable: string
  is_default: boolean
  is_active: boolean
}

interface BaiduPCSAuthStatus {
  authenticated: boolean
  message: string
  user_info?: {
    user_id: number
    user_name: string
    quota_used: number
    quota_total: number
    quota_used_readable: string
    quota_total_readable: string
    quota_usage_percent: number
  }
  setup_guide?: {
    steps: string[]
    required_cookies: string[]
    tips: string[]
  }
}

interface UsageGuide {
  title: string
  description: string
  setup_steps: Array<{
    step: number
    title: string
    description: string
    example?: any
    features?: string[]
  }>
  advantages: string[]
  required_data: {
    cookies: {
      description: string
      format: string
      required_fields: string[]
      optional_fields: string[]
    }
    bduss: {
      description: string
      note: string
    }
  }
}

const BaiduPanForm: React.FC = () => {
  const [loading, setLoading] = useState(true)
  const [authStatus, setAuthStatus] = useState<BaiduPCSAuthStatus | null>(null)
  const [users, setUsers] = useState<BaiduPCSUser[]>([])
  const [cookieInput, setCookieInput] = useState('')
  const [bdussInput, setBdussInput] = useState('')
  const [adding, setAdding] = useState(false)
  const [removing, setRemoving] = useState<number | null>(null)
  const [showGuide, setShowGuide] = useState(false)
  const [usageGuide, setUsageGuide] = useState<UsageGuide | null>(null)

  // 获取认证状态
  const loadAuthStatus = async () => {
    try {
      setLoading(true)
      const response = await fetch('/api/baidupcs/auth_status')
      const result = await response.json()
      
      if (result.code === 0) {
        setAuthStatus(result.data)
      } else {
        toast.error(result.message || '获取认证状态失败')
      }
    } catch (error) {
      console.error('获取BaiduPCS认证状态失败:', error)
      toast.error('获取认证状态失败')
    } finally {
      setLoading(false)
    }
  }

  // 获取用户列表
  const loadUsers = async () => {
    try {
      const response = await fetch('/api/baidupcs/users')
      const result = await response.json()
      
      if (result.code === 0) {
        setUsers(result.data.users || [])
      }
    } catch (error) {
      console.error('获取用户列表失败:', error)
    }
  }

  // 获取使用指南
  const loadUsageGuide = async () => {
    try {
      const response = await fetch('/api/baidupcs/usage_guide')
      const result = await response.json()
      
      if (result.code === 0) {
        setUsageGuide(result.data)
      }
    } catch (error) {
      console.error('获取使用指南失败:', error)
    }
  }

  // 添加用户
  const addUser = async () => {
    if (!cookieInput.trim()) {
      toast.error('请输入完整的Cookie字符串')
      return
    }

    setAdding(true)
    try {
      const response = await fetch('/api/baidupcs/add_user', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          cookies: cookieInput.trim(),
          bduss: bdussInput.trim() || undefined
        }),
      })
      
      const result = await response.json()
      
      if (result.code === 0) {
        toast.success('百度网盘用户添加成功')
        setCookieInput('')
        setBdussInput('')
        await loadAuthStatus()
        await loadUsers()
      } else {
        toast.error(result.message || '添加用户失败')
      }
    } catch (error) {
      console.error('添加用户失败:', error)
      toast.error('添加用户失败，请稍后重试')
    } finally {
      setAdding(false)
    }
  }

  // 移除用户
  const removeUser = async (userId?: number) => {
    setRemoving(userId || 0)
    try {
      const response = await fetch('/api/baidupcs/remove_user', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ user_id: userId }),
      })
      
      const result = await response.json()
      
      if (result.code === 0) {
        toast.success('用户移除成功')
        await loadAuthStatus()
        await loadUsers()
      } else {
        toast.error(result.message || '移除用户失败')
      }
    } catch (error) {
      console.error('移除用户失败:', error)
      toast.error('移除用户失败，请稍后重试')
    } finally {
      setRemoving(null)
    }
  }

  useEffect(() => {
    loadAuthStatus()
    loadUsers()
    loadUsageGuide()
  }, [])

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-4 max-h-screen overflow-y-auto">
      {/* 头部 */}
      <div className="flex items-center space-x-3">
        <BaiduPanLogo />
        <div>
          <h1 className="text-xl font-bold text-gray-900">百度网盘设置 (BaiduPCS-Py)</h1>
          <p className="text-sm text-gray-600">基于官方BaiduPCS-Py库，支持多用户管理和完整的网盘操作</p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <LoaderIcon className="w-8 h-8 animate-spin text-blue-500" />
          <span className="ml-2 text-gray-600">加载中...</span>
        </div>
      ) : (
        <>
          {/* 认证状态 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <UserIcon className="w-5 h-5" />
                <span>认证状态</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    loadAuthStatus()
                    loadUsers()
                  }}
                  className="ml-auto"
                >
                  <RefreshCwIcon className="w-4 h-4" />
                  刷新
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {authStatus?.authenticated ? (
                <Alert>
                  <CheckIcon className="w-4 h-4" />
                  <AlertDescription>
                    <div className="space-y-2">
                      <div className="font-medium text-green-700">
                        ✅ {authStatus.message}
                      </div>
                      {authStatus.user_info && (
                        <div className="text-sm text-gray-600 space-y-1">
                          <div>用户: {authStatus.user_info.user_name} (ID: {authStatus.user_info.user_id})</div>
                          <div>
                            存储: {authStatus.user_info.quota_used_readable} / {authStatus.user_info.quota_total_readable}
                            <span className="ml-2 text-blue-600">
                              ({authStatus.user_info.quota_usage_percent.toFixed(1)}%)
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  </AlertDescription>
                </Alert>
              ) : (
                <Alert variant="destructive">
                  <AlertCircleIcon className="w-4 h-4" />
                  <AlertDescription>
                    <div className="font-medium">❌ {authStatus?.message || '未认证'}</div>
                    <div className="text-sm mt-2">
                      请按照下方指南添加百度网盘用户
                    </div>
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          {/* 用户列表 */}
          {users.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>已添加的用户</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {users.map((user) => (
                    <div 
                      key={user.user_id}
                      className="flex items-center justify-between p-3 border rounded-lg"
                    >
                      <div className="flex items-center space-x-3">
                        <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                          <UserIcon className="w-5 h-5 text-blue-600" />
                        </div>
                        <div>
                          <div className="font-medium">{user.user_name}</div>
                          <div className="text-sm text-gray-500">
                            ID: {user.user_id} | 
                            存储: {user.quota_used_readable} / {user.quota_total_readable}
                          </div>
                        </div>
                        {user.is_default && (
                          <Badge variant="default">默认用户</Badge>
                        )}
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => removeUser(user.user_id)}
                        disabled={removing === user.user_id}
                        className="text-red-600 hover:text-red-700"
                      >
                        {removing === user.user_id ? (
                          <LoaderIcon className="w-4 h-4 animate-spin" />
                        ) : (
                          <TrashIcon className="w-4 h-4" />
                        )}
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* 添加用户 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <PlusIcon className="w-5 h-5" />
                <span>添加用户</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="cookies">Cookie字符串 *</Label>
                <Textarea
                  id="cookies"
                  value={cookieInput}
                  onChange={(e) => setCookieInput(e.target.value)}
                  placeholder="请输入完整的百度网盘Cookie字符串，格式如：BDUSS=xxx; STOKEN=xxx; PSTM=xxx; BAIDUID=xxx; ..."
                  rows={2}
                  className="font-mono text-sm resize-none"
                />
                <div className="text-xs text-gray-500">
                  必须包含 BDUSS 字段，其他字段可选但建议包含完整Cookie
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="bduss">BDUSS (可选)</Label>
                <Input
                  id="bduss"
                  value={bdussInput}
                  onChange={(e) => setBdussInput(e.target.value)}
                  placeholder="如果Cookie中已包含BDUSS，此处可不填"
                  className="font-mono text-sm"
                />
                <div className="text-xs text-gray-500">
                  如果Cookie字符串中已包含BDUSS，则此字段可以留空
                </div>
              </div>

              <Button 
                onClick={addUser}
                disabled={adding || !cookieInput.trim()}
                className="w-full"
              >
                {adding ? (
                  <>
                    <LoaderIcon className="w-4 h-4 animate-spin mr-2" />
                    添加中...
                  </>
                ) : (
                  <>
                    <PlusIcon className="w-4 h-4 mr-2" />
                    添加用户
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* 使用指南 */}
          {usageGuide && (
            <Card>
              <CardHeader>
                <CardTitle 
                  className="cursor-pointer flex items-center justify-between"
                  onClick={() => setShowGuide(!showGuide)}
                >
                  <span>使用指南</span>
                  <Button variant="ghost" size="sm">
                    {showGuide ? '收起' : '展开'}
                  </Button>
                </CardTitle>
              </CardHeader>
              {showGuide && (
                <CardContent className="space-y-4 max-h-96 overflow-y-auto">
                  <div>
                    <h3 className="font-medium text-base mb-2">{usageGuide.title}</h3>
                    <p className="text-sm text-gray-600 mb-3">{usageGuide.description}</p>
                  </div>

                  <div>
                    <h4 className="font-medium text-sm mb-2">设置步骤：</h4>
                    <div className="space-y-2">
                      {usageGuide.setup_steps.map((step) => (
                        <div key={step.step} className="border-l-4 border-blue-500 pl-3">
                          <div className="font-medium text-sm">
                            步骤 {step.step}: {step.title}
                          </div>
                          <div className="text-xs text-gray-600 mt-1">
                            {step.description}
                          </div>
                          {step.features && (
                            <div className="mt-1">
                              <div className="text-xs font-medium">功能：</div>
                              <ul className="text-xs text-gray-600 ml-3">
                                {step.features.map((feature, index) => (
                                  <li key={index} className="list-disc">{feature}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h4 className="font-medium text-sm mb-2">优势：</h4>
                    <ul className="space-y-1">
                      {usageGuide.advantages.map((advantage, index) => (
                        <li key={index} className="flex items-start space-x-2">
                          <CheckIcon className="w-3 h-3 text-green-500 mt-0.5 flex-shrink-0" />
                          <span className="text-xs text-gray-600">{advantage}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <h4 className="font-medium text-sm mb-2">所需数据：</h4>
                    <div className="space-y-2">
                      <div className="bg-gray-50 p-2 rounded">
                        <div className="font-medium text-xs">Cookie字符串</div>
                        <div className="text-xs text-gray-600 mt-1">
                          {usageGuide.required_data.cookies.description}
                        </div>
                        <div className="text-xs font-mono bg-white p-1 rounded mt-1 break-all">
                          {usageGuide.required_data.cookies.format}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          必需字段: {usageGuide.required_data.cookies.required_fields.join(', ')}
                        </div>
                      </div>
                      <div className="bg-gray-50 p-2 rounded">
                        <div className="font-medium text-xs">BDUSS</div>
                        <div className="text-xs text-gray-600 mt-1">
                          {usageGuide.required_data.bduss.description}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          {usageGuide.required_data.bduss.note}
                        </div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  )
}

export default BaiduPanForm 