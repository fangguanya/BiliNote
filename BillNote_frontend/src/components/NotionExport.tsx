import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogFooter, 
  DialogHeader, 
  DialogTitle, 
  DialogTrigger 
} from '@/components/ui/dialog'
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Loader2, ExternalLink, Database, FileText } from 'lucide-react'
import { toast } from 'sonner'
import { 
  testNotionConnection, 
  getNotionDatabases, 
  saveNoteToNotion,
  checkNotionHealth,
  debugApiConnection,
  NotionDatabase 
} from '@/services/notion'
import { useTaskStore } from '@/store/taskStore'
import { useSystemStore } from '@/store/configStore'

interface NotionExportProps {
  taskId: string
  noteTitle?: string
  disabled?: boolean
}

const NotionExport: React.FC<NotionExportProps> = ({ 
  taskId, 
  noteTitle = '未命名笔记', 
  disabled = false 
}) => {
  const { updateTaskNotion } = useTaskStore()
  const { notionConfig } = useSystemStore()
  const [isOpen, setIsOpen] = useState(false)
  const [databases, setDatabases] = useState<NotionDatabase[]>([])
  const [selectedDatabaseId, setSelectedDatabaseId] = useState(notionConfig.defaultDatabaseId)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isLoadingDatabases, setIsLoadingDatabases] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [saveMode, setSaveMode] = useState<'database' | 'standalone'>(notionConfig.defaultSaveMode)

  // 检查配置并初始化
  useEffect(() => {
    if (notionConfig.token) {
      checkConnection()
      setSelectedDatabaseId(notionConfig.defaultDatabaseId)
      setSaveMode(notionConfig.defaultSaveMode)
    }
  }, [notionConfig])

  // 检查连接状态
  const checkConnection = async () => {
    if (!notionConfig.token) return
    
    try {
      const result = await testNotionConnection(notionConfig.token)
      setIsConnected(result?.connected || false)
      if (result?.connected) {
        await loadDatabases()
      }
    } catch (error) {
      setIsConnected(false)
    }
  }

  // 测试连接（如果没有配置，跳转到设置页面）
  const handleTestConnection = async () => {
    if (!notionConfig.token) {
      toast.error('请先在设置中配置Notion令牌', {
        action: {
          label: '前往设置',
          onClick: () => window.open('#/settings/notion', '_blank')
        }
      })
      return
    }

    setIsConnecting(true)
    try {
      await checkConnection()
    } finally {
      setIsConnecting(false)
    }
  }

  // 加载数据库列表
  const loadDatabases = async () => {
    if (!notionConfig.token) return

    setIsLoadingDatabases(true)
    try {
      const databaseList = await getNotionDatabases(notionConfig.token)
      setDatabases(databaseList)
      if (databaseList.length === 0) {
        toast.info('未找到可用的数据库，建议创建独立页面')
        setSaveMode('standalone')
      }
    } catch (error) {
      console.error('加载数据库失败:', error)
    } finally {
      setIsLoadingDatabases(false)
    }
  }

  // 保存到Notion
  const handleSaveToNotion = async () => {
    if (!notionConfig.token) {
      toast.error('请先在设置中配置Notion令牌')
      return
    }

    if (saveMode === 'database' && !selectedDatabaseId) {
      toast.error('请选择数据库')
      return
    }

    setIsSaving(true)
    try {
      const result = await saveNoteToNotion({
        taskId,
        token: notionConfig.token,
        databaseId: saveMode === 'database' ? selectedDatabaseId : undefined
      })

      if (result) {
        // 更新任务的Notion状态
        updateTaskNotion(taskId, {
          saved: true,
          pageId: result.page_id,
          pageUrl: result.url,
          savedAt: new Date().toISOString()
        })

        toast.success(
          <div className="flex flex-col gap-1">
            <span>笔记已保存到Notion！</span>
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs underline"
              onClick={() => window.open(result.url, '_blank')}
            >
              <ExternalLink className="w-3 h-3 mr-1" />
              打开页面
            </Button>
          </div>
        )
        setIsOpen(false)
      }
    } catch (error) {
      console.error('保存失败:', error)
    } finally {
      setIsSaving(false)
    }
  }

  // 重置状态
  const handleOpenChange = (open: boolean) => {
    setIsOpen(open)
    if (!open) {
      // 对话框关闭时不重置连接状态，保持用户体验
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          className="flex items-center gap-2"
        >
          <FileText className="w-4 h-4" />
          保存到Notion
        </Button>
      </DialogTrigger>
      
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>保存到Notion</DialogTitle>
          <DialogDescription>
            将笔记 "{noteTitle}" 保存到你的Notion工作区
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 配置状态检查 */}
          {!notionConfig.token && (
            <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
              <div className="flex items-center gap-2 text-yellow-800">
                <FileText className="w-4 h-4" />
                <span className="font-medium">需要配置Notion集成</span>
              </div>
              <p className="text-sm text-yellow-700 mt-1">
                请先在设置中配置Notion令牌和默认保存方式
              </p>
              <Button
                size="sm"
                variant="outline"
                className="mt-2"
                onClick={() => window.open('#/settings/notion', '_blank')}
              >
                前往设置
              </Button>
            </div>
          )}

          {notionConfig.token && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">连接状态</span>
                <Button
                  onClick={handleTestConnection}
                  disabled={isConnecting}
                  size="sm"
                  variant="outline"
                >
                  {isConnecting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    '重新检查'
                  )}
                </Button>
              </div>
              {isConnected ? (
                <p className="text-sm text-green-600">✅ 已连接到Notion</p>
              ) : (
                <p className="text-sm text-red-600">❌ 连接失败，请检查配置</p>
              )}
            </div>
          )}

          {/* 保存模式选择 */}
          {isConnected && (
            <div className="space-y-2">
              <Label>保存方式</Label>
              <Select value={saveMode} onValueChange={(value: 'database' | 'standalone') => setSaveMode(value)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="database">
                    <div className="flex items-center gap-2">
                      <Database className="w-4 h-4" />
                      保存到数据库
                    </div>
                  </SelectItem>
                  <SelectItem value="standalone">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      创建独立页面
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* 数据库选择 */}
          {isConnected && saveMode === 'database' && (
            <div className="space-y-2">
              <Label htmlFor="database">选择数据库</Label>
              <div className="flex gap-2">
                <Select value={selectedDatabaseId} onValueChange={setSelectedDatabaseId}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="选择数据库" />
                  </SelectTrigger>
                  <SelectContent>
                    {databases.map((db) => (
                      <SelectItem key={db.id} value={db.id}>
                        <div className="flex flex-col">
                          <span>{db.title}</span>
                          <span className="text-xs text-muted-foreground">
                            {new Date(db.last_edited_time).toLocaleDateString()}
                          </span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  onClick={loadDatabases}
                  disabled={isLoadingDatabases}
                  size="sm"
                  variant="outline"
                >
                  {isLoadingDatabases ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    '刷新'
                  )}
                </Button>
              </div>
              {databases.length === 0 && !isLoadingDatabases && (
                <p className="text-sm text-muted-foreground">
                  未找到数据库，请在Notion中创建数据库后重试
                </p>
              )}
            </div>
          )}

          {/* 独立页面说明 */}
          {isConnected && saveMode === 'standalone' && (
            <div className="p-3 bg-blue-50 rounded-lg">
              <p className="text-sm text-blue-700">
                将在你的Notion工作区根目录创建一个独立页面
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => setIsOpen(false)}
          >
            取消
          </Button>
          <Button
            onClick={handleSaveToNotion}
            disabled={!isConnected || isSaving}
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                保存中...
              </>
            ) : (
              '保存到Notion'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default NotionExport 