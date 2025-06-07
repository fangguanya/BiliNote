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
  NotionDatabase 
} from '@/services/notion'

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
  const [isOpen, setIsOpen] = useState(false)
  const [token, setToken] = useState('')
  const [databases, setDatabases] = useState<NotionDatabase[]>([])
  const [selectedDatabaseId, setSelectedDatabaseId] = useState<string>('')
  const [isConnecting, setIsConnecting] = useState(false)
  const [isLoadingDatabases, setIsLoadingDatabases] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [saveMode, setSaveMode] = useState<'database' | 'standalone'>('database')

  // 从localStorage读取保存的token
  useEffect(() => {
    const savedToken = localStorage.getItem('notion_token')
    if (savedToken) {
      setToken(savedToken)
    }
  }, [])

  // 测试连接
  const handleTestConnection = async () => {
    if (!token.trim()) {
      toast.error('请输入Notion令牌')
      return
    }

    setIsConnecting(true)
    try {
      const result = await testNotionConnection(token.trim())
      if (result?.connected) {
        setIsConnected(true)
        // 保存token到localStorage
        localStorage.setItem('notion_token', token.trim())
        // 自动加载数据库列表
        await loadDatabases()
      } else {
        setIsConnected(false)
      }
    } catch (error) {
      setIsConnected(false)
    } finally {
      setIsConnecting(false)
    }
  }

  // 加载数据库列表
  const loadDatabases = async () => {
    if (!token.trim()) return

    setIsLoadingDatabases(true)
    try {
      const databaseList = await getNotionDatabases(token.trim())
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
    if (!token.trim()) {
      toast.error('请输入Notion令牌')
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
        token: token.trim(),
        databaseId: saveMode === 'database' ? selectedDatabaseId : undefined
      })

      if (result) {
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
          {/* Token输入 */}
          <div className="space-y-2">
            <Label htmlFor="token">Notion集成令牌</Label>
            <div className="flex gap-2">
              <Input
                id="token"
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="输入你的Notion集成令牌"
                className="flex-1"
              />
              <Button
                onClick={handleTestConnection}
                disabled={isConnecting || !token.trim()}
                size="sm"
              >
                {isConnecting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  '测试连接'
                )}
              </Button>
            </div>
            {isConnected && (
              <p className="text-sm text-green-600">✅ 连接成功</p>
            )}
          </div>

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