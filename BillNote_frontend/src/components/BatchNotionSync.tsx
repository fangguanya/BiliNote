import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
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
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { 
  Loader2, 
  ExternalLink, 
  Database, 
  FileText, 
  Upload, 
  CheckCircle, 
  XCircle,
  RefreshCw
} from 'lucide-react'
import { toast } from 'sonner'
import { 
  testNotionConnection, 
  getNotionDatabases, 
  batchSyncToNotion,
  NotionDatabase,
  BatchSyncToNotionResult
} from '@/services/notion'
import { useTaskStore, Task } from '@/store/taskStore'
import { useSystemStore } from '@/store/configStore'

interface BatchNotionSyncProps {
  disabled?: boolean
}

const BatchNotionSync: React.FC<BatchNotionSyncProps> = ({ disabled = false }) => {
  const { tasks, updateTaskNotion } = useTaskStore()
  const { notionConfig } = useSystemStore()
  const [isOpen, setIsOpen] = useState(false)
  const [databases, setDatabases] = useState<NotionDatabase[]>([])
  const [selectedDatabaseId, setSelectedDatabaseId] = useState(notionConfig.defaultDatabaseId)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isLoadingDatabases, setIsLoadingDatabases] = useState(false)
  const [isSyncing, setIsSyncing] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [saveMode, setSaveMode] = useState<'database' | 'standalone'>(notionConfig.defaultSaveMode)
  const [syncProgress, setSyncProgress] = useState(0)
  const [syncResults, setSyncResults] = useState<BatchSyncToNotionResult | null>(null)

  // 获取所有未同步的成功任务
  const unsyncedTasks = tasks.filter(task => 
    task.status === 'SUCCESS' && 
    (!task.notion || !task.notion.saved)
  )

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

  // 测试连接
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

  // 批量同步到Notion
  const handleBatchSync = async () => {
    if (!notionConfig.token) {
      toast.error('请先在设置中配置Notion令牌')
      return
    }

    if (saveMode === 'database' && !selectedDatabaseId) {
      toast.error('请选择数据库')
      return
    }

    if (unsyncedTasks.length === 0) {
      toast.info('没有需要同步的笔记')
      return
    }

    setIsSyncing(true)
    setSyncProgress(0)
    setSyncResults(null)

    try {
      // 获取所有未同步任务的ID
      const taskIds = unsyncedTasks.map(task => task.id)

      // 调用批量同步API
      const result = await batchSyncToNotion({
        token: notionConfig.token,
        databaseId: saveMode === 'database' ? selectedDatabaseId : undefined,
        taskIds: taskIds
      })

      if (result) {
        setSyncResults(result)
        setSyncProgress(100)

        // 更新每个成功同步的任务状态
        result.results.forEach(syncResult => {
          if (syncResult.success) {
            updateTaskNotion(syncResult.task_id, {
              saved: true,
              pageId: syncResult.page_id!,
              pageUrl: syncResult.page_url!,
              savedAt: new Date().toISOString()
            })
          }
        })

        // 显示汇总toast
        if (result.success_count > 0) {
          toast.success(
            <div className="flex flex-col gap-2">
              <span>✅ 批量同步完成！</span>
              <span className="text-sm text-muted-foreground">
                成功: {result.success_count} 个，失败: {result.failed_count} 个
              </span>
              {result.success_count > 0 && (
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto p-0 text-xs underline"
                  onClick={() => {
                    // 打开第一个成功的页面作为示例
                    const firstSuccess = result.results.find(r => r.success && r.page_url)
                    if (firstSuccess) {
                      window.open(firstSuccess.page_url, '_blank')
                    }
                  }}
                >
                  <ExternalLink className="w-3 h-3 mr-1" />
                  查看同步页面
                </Button>
              )}
            </div>
          )
        }
      }
    } catch (error) {
      console.error('批量同步失败:', error)
      toast.error('批量同步失败，请重试')
    } finally {
      setIsSyncing(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button 
          variant="outline" 
          size="sm"
          disabled={disabled || unsyncedTasks.length === 0}
          className="flex items-center gap-2"
        >
          <Upload className="w-4 h-4" />
          批量同步到Notion
          {unsyncedTasks.length > 0 && (
            <Badge variant="secondary" className="ml-1">
              {unsyncedTasks.length}
            </Badge>
          )}
        </Button>
      </DialogTrigger>
      
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="w-5 h-5" />
            批量同步到Notion
          </DialogTitle>
          <DialogDescription>
            将所有未同步的笔记一键同步到Notion
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 同步统计 */}
          <div className="p-4 bg-muted/50 rounded-lg">
            <div className="flex items-center justify-between text-sm">
              <span>待同步笔记数量：</span>
              <Badge variant="outline">{unsyncedTasks.length} 个</Badge>
            </div>
          </div>

          {/* 连接状态 */}
          {!isConnected ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <XCircle className="w-4 h-4 text-destructive" />
                未连接到Notion
              </div>
              <Button 
                onClick={handleTestConnection} 
                disabled={isConnecting}
                size="sm"
                variant="outline"
                className="w-full"
              >
                {isConnecting ? (
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                ) : null}
                测试连接
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-green-600">
              <CheckCircle className="w-4 h-4" />
              已连接到Notion
            </div>
          )}

          {/* 保存方式选择 */}
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
                    <RefreshCw className="w-4 h-4" />
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

          {/* 同步进度 */}
          {isSyncing && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>同步进度</span>
                <span>{Math.round(syncProgress)}%</span>
              </div>
              <Progress value={syncProgress} className="w-full" />
            </div>
          )}

          {/* 同步结果 */}
          {syncResults && (
            <div className="space-y-2">
              <Label>同步结果</Label>
              <div className="p-3 bg-muted/50 rounded-lg space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span>总计：</span>
                  <Badge variant="outline">{syncResults.total} 个</Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span>成功：</span>
                  <Badge variant="default" className="bg-green-500">{syncResults.success_count} 个</Badge>
                </div>
                {syncResults.failed_count > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span>失败：</span>
                    <Badge variant="destructive">{syncResults.failed_count} 个</Badge>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button 
            variant="outline" 
            onClick={() => setIsOpen(false)}
            disabled={isSyncing}
          >
            取消
          </Button>
          <Button 
            onClick={handleBatchSync}
            disabled={!isConnected || isSyncing || unsyncedTasks.length === 0 || (saveMode === 'database' && !selectedDatabaseId)}
          >
            {isSyncing ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <Upload className="w-4 h-4 mr-2" />
            )}
            {isSyncing ? '同步中...' : `开始同步 (${unsyncedTasks.length} 个)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default BatchNotionSync 