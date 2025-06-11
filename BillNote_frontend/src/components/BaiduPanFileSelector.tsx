import React, { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { getBaiduPanAuthStatus, getBaiduPanFileList, selectBaiduPanFiles } from '@/services/note'
import { generateBaiduPanQr, checkBaiduPanLoginStatus } from '@/services/auth'
import { BaiduPanLogo } from '@/components/Icons/platform'
import toast from 'react-hot-toast'
import { 
  FolderIcon, 
  VideoIcon, 
  MusicIcon, 
  FileIcon, 
  ArrowLeftIcon,
  HomeIcon,
  LoaderIcon,
  CheckIcon,
  AlertCircleIcon,
  RefreshCwIcon
} from 'lucide-react'

interface BaiduPanFile {
  fs_id: string
  filename: string
  is_dir: boolean
  is_media: boolean
  size: number
  size_readable: string
  ctime: number
  path: string
}

interface BaiduPanFileSelectorProps {
  onTasksCreated?: (tasks: any[]) => void
  taskConfig: any
}

const BaiduPanFileSelector: React.FC<BaiduPanFileSelectorProps> = ({ 
  onTasksCreated, 
  taskConfig 
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)
  const [authLoading, setAuthLoading] = useState(false)
  const [currentPath, setCurrentPath] = useState('/')
  const [pathHistory, setPathHistory] = useState<string[]>(['/'])
  const [files, setFiles] = useState<BaiduPanFile[]>([])
  const [selectedFiles, setSelectedFiles] = useState<BaiduPanFile[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [mediaCount, setMediaCount] = useState(0)
  
  // 登录相关状态
  const [showLoginDialog, setShowLoginDialog] = useState(false)
  const [qrCode, setQrCode] = useState('')
  const [loginSessionId, setLoginSessionId] = useState('')
  const [loginChecking, setLoginChecking] = useState(false)
  
  // 存储清理函数的引用
  const cleanupRef = useRef<(() => void) | null>(null)

  // 检查认证状态
  const checkAuthStatus = async () => {
    setAuthLoading(true)
    try {
      console.log('🔍 开始检查认证状态')
      const result = await getBaiduPanAuthStatus()
      console.log('📋 认证状态结果:', result)
      
      if (result && result.code === 0) {
        const isAuth = result.data?.authenticated || false
        setAuthenticated(isAuth)
        console.log(`🔐 认证状态: ${isAuth}`)
        
        if (isAuth) {
          console.log('✅ 已认证，开始加载文件列表')
          await loadFiles('/')
        } else {
          // 认证失败，清空文件列表
          console.log('❌ 未认证，清空文件列表')
          setFiles([])
          setMediaCount(0)
        }
      } else {
        console.warn('⚠️ 认证状态检查返回异常结果:', result)
        setAuthenticated(false)
        setFiles([])
        setMediaCount(0)
        if (result?.message) {
          toast.error(`认证检查失败: ${result.message}`)
        }
      }
    } catch (error: any) {
      console.error('❌ 检查认证状态失败:', error)
      setAuthenticated(false)
      setFiles([])
      setMediaCount(0)
      const errorMessage = error.response?.data?.message || error.message || '未知错误'
      toast.error(`认证状态检查失败: ${errorMessage}`)
    } finally {
      setAuthLoading(false)
    }
  }

  // 加载文件列表
  const loadFiles = async (path: string) => {
    setLoading(true)
    try {
      console.log('🗂️ 开始加载文件列表:', path)
      const result = await getBaiduPanFileList(path)
      console.log('📋 文件列表结果:', result)
      
      if (result && result.files) {
        setFiles(result.files)
        setMediaCount(result.media_count || 0)
        setCurrentPath(path)
        console.log(`✅ 文件列表加载成功: ${result.files.length} 个文件，${result.media_count || 0} 个媒体文件`)
      } else {
        console.warn('⚠️ 文件列表结果格式异常:', result)
        setFiles([])
        setMediaCount(0)
        toast.error('文件列表格式异常')
      }
    } catch (error: any) {
      console.error('❌ 加载文件列表失败:', error)
      
      // 检查是否是认证错误
      if (error.response?.status === 401 || 
          error.response?.data?.message?.includes('认证') ||
          error.response?.data?.message?.includes('登录')) {
        setAuthenticated(false)
        toast.error('百度网盘认证已过期，请重新登录')
      } else {
        const errorMessage = error.response?.data?.message || error.message || '未知错误'
        toast.error(`加载文件列表失败: ${errorMessage}`)
      }
      setFiles([])
      setMediaCount(0)
    } finally {
      setLoading(false)
    }
  }

  // 进入文件夹
  const enterFolder = (folderPath: string) => {
    const newHistory = [...pathHistory, folderPath]
    setPathHistory(newHistory)
    loadFiles(folderPath)
  }

  // 返回上级目录
  const goBack = () => {
    if (pathHistory.length > 1) {
      const newHistory = pathHistory.slice(0, -1)
      setPathHistory(newHistory)
      const previousPath = newHistory[newHistory.length - 1]
      loadFiles(previousPath)
    }
  }

  // 返回根目录
  const goHome = () => {
    setPathHistory(['/'])
    loadFiles('/')
  }

  // 切换文件选择
  const toggleFileSelection = (file: BaiduPanFile) => {
    console.log('🎯 尝试切换文件选择:', file.filename, 'is_media:', file.is_media)
    
    if (!file.is_media) {
      console.log('⚠️ 非媒体文件，跳过选择:', file.filename)
      return // 只能选择媒体文件
    }
    
    const isSelected = selectedFiles.some(f => f.fs_id === file.fs_id)
    console.log(`🔄 文件选择状态变化: ${file.filename} ${isSelected ? '取消选择' : '选择'}`)
    
    if (isSelected) {
      setSelectedFiles(prev => {
        const newFiles = prev.filter(f => f.fs_id !== file.fs_id)
        console.log('📤 更新选择列表，移除文件，当前选择数量:', newFiles.length)
        return newFiles
      })
    } else {
      setSelectedFiles(prev => {
        const newFiles = [...prev, file]
        console.log('📥 更新选择列表，添加文件，当前选择数量:', newFiles.length)
        return newFiles
      })
    }
  }

  // 全选/取消全选媒体文件
  const toggleSelectAll = () => {
    const mediaFiles = files.filter(f => f.is_media)
    const allSelected = mediaFiles.every(f => selectedFiles.some(sf => sf.fs_id === f.fs_id))
    
    if (allSelected) {
      // 取消全选
      setSelectedFiles(prev => prev.filter(sf => !mediaFiles.some(mf => mf.fs_id === sf.fs_id)))
    } else {
      // 全选
      const newSelected = [...selectedFiles]
      mediaFiles.forEach(mf => {
        if (!newSelected.some(sf => sf.fs_id === mf.fs_id)) {
          newSelected.push(mf)
        }
      })
      setSelectedFiles(newSelected)
    }
  }

  // 创建任务
  const createTasks = async () => {
    if (selectedFiles.length === 0) {
      toast.error('请选择至少一个媒体文件')
      return
    }

    setCreating(true)
    try {
      const result = await selectBaiduPanFiles(selectedFiles, taskConfig)
      
      if (onTasksCreated) {
        onTasksCreated(result.created_tasks)
      }
      
      // 清空选择
      setSelectedFiles([])
      setIsOpen(false)
      
    } catch (error) {
      console.error('创建任务失败:', error)
    } finally {
      setCreating(false)
    }
  }

  // 百度网盘登录
  const startBaiduPanLogin = async () => {
    try {
      setShowLoginDialog(true)
      const result = await generateBaiduPanQr()
      
      if (result) {
        const data = result
        console.log('🔍 百度网盘二维码数据:', data)
        console.log('🖼️ 二维码字段检查:', {
          qr_code: data.qr_code,
          session_id: data.session_id,
          expires_in: data.expires_in
        })
        
        const qrCodeUrl = data.qr_code
        console.log('✅ 最终使用的二维码URL:', qrCodeUrl)
        
        setQrCode(qrCodeUrl)
        setLoginSessionId(data.session_id)
        
        // 开始轮询检查登录状态
        cleanupRef.current = startLoginStatusCheck(data.session_id)
      } else {
        toast.error((result as any)?.message || '生成登录二维码失败')
        setShowLoginDialog(false)
      }
    } catch (error) {
      console.error('启动百度网盘登录失败:', error)
      toast.error('启动登录失败')
      setShowLoginDialog(false)
    }
  }

  // 轮询检查登录状态
  const startLoginStatusCheck = (sessionId: string) => {
    setLoginChecking(true)
    
    const checkInterval = setInterval(async () => {
      try {
        const result = await checkBaiduPanLoginStatus(sessionId)
        
        if (result) {
          const data = result
          if (data.status === 'success') {
            clearInterval(checkInterval)
            setLoginChecking(false)
            setShowLoginDialog(false)
            toast.success('百度网盘登录成功！')
            
            // 直接更新认证状态并加载文件，避免循环调用
            setAuthenticated(true)
            await loadFiles('/')
          } else if (data.status === 'failed') {
            clearInterval(checkInterval)
            setLoginChecking(false)
            toast.error(data.message || '登录失败')
          } else if (data.status === 'expired') {
            clearInterval(checkInterval)
            setLoginChecking(false)
            setShowLoginDialog(false)
            toast.error('登录验证已过期，请重新扫码')
            // 3秒后自动重新打开登录对话框
            setTimeout(() => {
              startBaiduPanLogin()
            }, 3000)
          }
        }
      } catch (error) {
        console.error('检查登录状态失败:', error)
        clearInterval(checkInterval)
        setLoginChecking(false)
      }
    }, 1000) // 每1秒检查一次，更快响应

    // 5分钟后停止检查
    const timeoutId = setTimeout(() => {
      clearInterval(checkInterval)
      setLoginChecking(false)
      if (showLoginDialog) {
        toast.error('登录超时，请重新扫码')
      }
    }, 300000)

    // 返回清理函数
    return () => {
      clearInterval(checkInterval)
      clearTimeout(timeoutId)
    }
  }

  // 组件挂载时检查认证状态
  useEffect(() => {
    if (isOpen) {
      checkAuthStatus()
    } else {
      // 关闭时清理登录检查
      if (cleanupRef.current) {
        cleanupRef.current()
        cleanupRef.current = null
      }
      setShowLoginDialog(false)
      setLoginChecking(false)
      setQrCode('')
      setLoginSessionId('')
    }
    
    // 组件卸载时清理
    return () => {
      if (cleanupRef.current) {
        cleanupRef.current()
        cleanupRef.current = null
      }
    }
  }, [isOpen])

  // 获取文件图标
  const getFileIcon = (file: BaiduPanFile) => {
    if (file.is_dir) {
      return <FolderIcon className="w-4 h-4 text-blue-500" />
    }
    
    const ext = file.filename.split('.').pop()?.toLowerCase()
    if (['mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'm4v', '3gp', 'ts', 'm2ts'].includes(ext || '')) {
      return <VideoIcon className="w-4 h-4 text-green-500" />
    }
    if (['mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a'].includes(ext || '')) {
      return <MusicIcon className="w-4 h-4 text-purple-500" />
    }
    
    return <FileIcon className="w-4 h-4 text-gray-400" />
  }

  // 格式化时间
  const formatTime = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleDateString('zh-CN')
  }

  const mediaFiles = files.filter(f => f.is_media)
  const allMediaSelected = mediaFiles.length > 0 && mediaFiles.every(f => selectedFiles.some(sf => sf.fs_id === f.fs_id))

  return (
    <>
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogTrigger asChild>
          <Button 
            variant="outline" 
            className="flex items-center gap-2 h-9"
            onClick={() => setIsOpen(true)}
          >
            <BaiduPanLogo />
            <span className="text-sm">选择百度网盘文件</span>
          </Button>
        </DialogTrigger>
        
        <DialogContent className="max-w-4xl max-h-[80vh]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <BaiduPanLogo />
              百度网盘文件选择器
            </DialogTitle>
          </DialogHeader>

          {authLoading ? (
            <div className="flex justify-center items-center py-8">
              <LoaderIcon className="w-6 h-6 animate-spin" />
              <span className="ml-2">检查认证状态...</span>
            </div>
          ) : !authenticated ? (
            <div className="text-center py-8">
              <Alert className="mb-4">
                <AlertCircleIcon className="h-4 w-4" />
                <AlertDescription>
                  需要登录百度网盘才能访问文件
                </AlertDescription>
              </Alert>
              
              <Button
                onClick={startBaiduPanLogin}
                className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700"
                disabled={loginChecking}
              >
                {loginChecking ? (
                  <>
                    <LoaderIcon className="w-4 h-4 animate-spin" />
                    登录中...
                  </>
                ) : (
                  <>
                    <BaiduPanLogo />
                    登录百度网盘
                  </>
                )}
              </Button>
              
              <div className="mt-4 text-xs text-gray-500">
                登录后可以浏览和下载百度网盘中的视频文件
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* 路径导航 */}
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={goHome}
                  className="h-6 px-2"
                >
                  <HomeIcon className="w-3 h-3" />
                </Button>
                
                {pathHistory.length > 1 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={goBack}
                    className="h-6 px-2"
                  >
                    <ArrowLeftIcon className="w-3 h-3" />
                  </Button>
                )}
                
                <span className="truncate">当前路径: {currentPath}</span>
                
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => loadFiles(currentPath)}
                  className="h-6 px-2"
                >
                  <RefreshCwIcon className="w-3 h-3" />
                </Button>
              </div>

              {/* 文件统计和批量选择 */}
              {files.length > 0 && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-gray-600">
                      共 {files.length} 个项目，{mediaCount} 个媒体文件
                    </span>
                    
                    {mediaCount > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={toggleSelectAll}
                        className="h-7 text-xs"
                      >
                        {allMediaSelected ? '取消全选' : '全选媒体文件'}
                      </Button>
                    )}
                  </div>
                  
                  {selectedFiles.length > 0 && (
                    <Badge variant="secondary">
                      已选择 {selectedFiles.length} 个文件
                    </Badge>
                  )}
                </div>
              )}

              {/* 文件列表 */}
              <ScrollArea className="h-96 border rounded-md p-2">
                {loading ? (
                  <div className="flex justify-center items-center py-8">
                    <LoaderIcon className="w-6 h-6 animate-spin" />
                    <span className="ml-2">加载中...</span>
                  </div>
                ) : files.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    当前目录为空
                  </div>
                ) : (
                  <div className="space-y-1">
                    {files.map((file) => (
                      <Card
                        key={file.fs_id}
                        className={`cursor-pointer transition-colors ${
                          file.is_dir ? 'hover:bg-blue-50' : 
                          file.is_media ? 'hover:bg-green-50' : 'hover:bg-gray-50'
                        } ${selectedFiles.some(sf => sf.fs_id === file.fs_id) ? 'bg-blue-100' : ''}`}
                        onClick={() => {
                          if (file.is_dir) {
                            enterFolder(file.path)
                          } else if (file.is_media) {
                            toggleFileSelection(file)
                          }
                        }}
                      >
                        <CardContent className="p-3">
                          <div className="flex items-center gap-3">
                            {file.is_media && !file.is_dir && (
                              <Checkbox
                                checked={selectedFiles.some(sf => sf.fs_id === file.fs_id)}
                                onCheckedChange={(checked) => {
                                  console.log('🔲 Checkbox状态变化:', file.filename, checked)
                                  toggleFileSelection(file)
                                }}
                                onClick={(e) => e.stopPropagation()}
                              />
                            )}
                            
                            {getFileIcon(file)}
                            
                            <div className="flex-1 min-w-0">
                              <p className="truncate font-medium text-sm">
                                {file.filename}
                              </p>
                              
                              <div className="flex items-center gap-4 text-xs text-gray-500 mt-1">
                                {!file.is_dir && (
                                  <span>{file.size_readable || '未知大小'}</span>
                                )}
                                <span>{formatTime(file.ctime)}</span>
                                
                                {file.is_media && (
                                  <Badge variant="outline" className="text-xs">
                                    媒体文件
                                  </Badge>
                                )}
                              </div>
                            </div>
                            
                            {selectedFiles.some(sf => sf.fs_id === file.fs_id) && (
                              <CheckIcon className="w-4 h-4 text-green-500" />
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </ScrollArea>

              {/* 操作按钮 */}
              <div className="flex justify-between items-center pt-4 border-t">
                <div className="text-sm text-gray-600">
                  {selectedFiles.length > 0 && (
                    <span>已选择 {selectedFiles.length} 个文件</span>
                  )}
                </div>
                
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setSelectedFiles([])
                      setIsOpen(false)
                    }}
                  >
                    取消
                  </Button>
                  
                  <Button
                    onClick={createTasks}
                    disabled={selectedFiles.length === 0 || creating}
                    className="flex items-center gap-2"
                  >
                    {creating ? (
                      <>
                        <LoaderIcon className="w-4 h-4 animate-spin" />
                        创建中...
                      </>
                    ) : (
                      `创建 ${selectedFiles.length} 个任务`
                    )}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* 百度网盘登录对话框 */}
      <Dialog open={showLoginDialog} onOpenChange={setShowLoginDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <BaiduPanLogo />
              百度网盘登录
            </DialogTitle>
          </DialogHeader>
          
          <div className="text-center space-y-4">
            {qrCode ? (
              <div className="flex justify-center">
                <img 
                  src={qrCode.startsWith('data:') ? qrCode : `data:image/png;base64,${qrCode}`}
                  alt="百度网盘登录二维码"
                  className="w-48 h-48 border rounded-md"
                  onError={(e) => {
                    console.error('❌ 二维码图片加载失败:', qrCode)
                    console.error('❌ 图片错误事件:', e)
                  }}
                  onLoad={() => {
                    console.log('✅ 二维码图片加载成功:', qrCode.substring(0, 50) + '...')
                  }}
                />
              </div>
            ) : (
              <div className="flex justify-center items-center h-48 w-48 mx-auto border rounded-md bg-gray-50">
                <div className="text-center">
                  <LoaderIcon className="w-8 h-8 animate-spin mx-auto mb-2 text-gray-400" />
                  <p className="text-sm text-gray-500">生成二维码中...</p>
                </div>
              </div>
            )}
            
            <p className="text-sm text-gray-600">
              {loginChecking ? '等待扫码确认...' : '请使用百度APP扫描二维码登录'}
            </p>
            
            {/* 调试信息 */}
            {process.env.NODE_ENV === 'development' && (
              <div className="text-xs text-gray-400 mt-2">
                <p>二维码状态: {qrCode ? '已生成' : '未生成'}</p>
                <p>会话ID: {loginSessionId}</p>
                <p>登录检查中: {loginChecking ? '是' : '否'}</p>
              </div>
            )}
            
            {loginChecking && (
              <div className="flex justify-center">
                <LoaderIcon className="w-5 h-5 animate-spin" />
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default BaiduPanFileSelector 