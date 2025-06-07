import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Loader2, Database, FileText, TestTube, RefreshCw, ExternalLink, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { 
  testNotionConnection, 
  getNotionDatabases,
  NotionDatabase 
} from '@/services/notion'
import { useSystemStore } from '@/store/configStore'
import BatchNotionSync from '@/components/BatchNotionSync'
import ForceBatchNotionSync from '@/components/ForceBatchNotionSync'

const NotionSettings: React.FC = () => {
  const { notionConfig, setNotionConfig } = useSystemStore()
  const [isConnecting, setIsConnecting] = useState(false)
  const [isLoadingDatabases, setIsLoadingDatabases] = useState(false)
  const [databases, setDatabases] = useState<NotionDatabase[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [tempToken, setTempToken] = useState(notionConfig.token)

  // 初始化时检查连接状态
  useEffect(() => {
    if (notionConfig.token) {
      setTempToken(notionConfig.token)
      checkConnection()
    }
  }, [])

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
    if (!tempToken.trim()) {
      toast.error('请输入Notion令牌')
      return
    }

    setIsConnecting(true)
    try {
      const result = await testNotionConnection(tempToken.trim())
      if (result?.connected) {
        setIsConnected(true)
        // 保存token到store
        setNotionConfig({ token: tempToken.trim() })
        // 自动加载数据库列表
        await loadDatabases()
      } else {
        setIsConnected(false)
      }
    } catch (error) {
      console.error('❌ 连接测试过程中出错:', error)
      setIsConnected(false)
    } finally {
      setIsConnecting(false)
    }
  }

  // 加载数据库列表
  const loadDatabases = async () => {
    const token = notionConfig.token || tempToken
    if (!token.trim()) return

    setIsLoadingDatabases(true)
    try {
      const databaseList = await getNotionDatabases(token.trim())
      setDatabases(databaseList)
      if (databaseList.length === 0) {
        toast.info('未找到可用的数据库')
      }
    } catch (error) {
      console.error('加载数据库失败:', error)
    } finally {
      setIsLoadingDatabases(false)
    }
  }

  // 保存配置
  const handleSaveConfig = () => {
    setNotionConfig({ token: tempToken.trim() })
    toast.success('Notion配置已保存')
  }

  // 清除配置
  const handleClearConfig = () => {
    setTempToken('')
    setNotionConfig({ 
      token: '', 
      defaultDatabaseId: '',
      defaultSaveMode: 'database'
    })
    setIsConnected(false)
    setDatabases([])
    toast.success('Notion配置已清除')
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Notion集成</h2>
        <p className="text-muted-foreground">配置Notion集成，自动保存生成的笔记</p>
      </div>

      <Separator />

      {/* 基础配置 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TestTube className="w-5 h-5" />
            连接配置
          </CardTitle>
          <CardDescription>
            配置Notion集成令牌以启用笔记同步功能
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 令牌输入 */}
          <div className="space-y-2">
            <Label htmlFor="token">Notion集成令牌</Label>
            <div className="flex gap-2">
              <Input
                id="token"
                type="password"
                placeholder="输入Notion集成令牌"
                value={tempToken}
                onChange={(e) => setTempToken(e.target.value)}
                className="flex-1"
              />
              <Button
                onClick={handleTestConnection}
                disabled={isConnecting || !tempToken.trim()}
                variant="outline"
              >
                {isConnecting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <TestTube className="w-4 h-4" />
                )}
                测试连接
              </Button>
            </div>
            {isConnected && (
              <p className="text-sm text-green-600">✅ 连接成功</p>
            )}
          </div>

          {/* 保存/清除按钮 */}
          <div className="flex gap-2">
            <Button onClick={handleSaveConfig} disabled={!tempToken.trim()}>
              保存配置
            </Button>
            <Button onClick={handleClearConfig} variant="outline">
              清除配置
            </Button>
          </div>

          {/* 获取令牌说明 */}
          <div className="p-4 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground mb-2">
              如何获取Notion集成令牌：
            </p>
            <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside">
              <li>访问 <Button variant="link" className="h-auto p-0 text-sm" onClick={() => window.open('https://www.notion.so/my-integrations', '_blank')}>
                <ExternalLink className="w-3 h-3 mr-1" />
                Notion集成页面
              </Button></li>
              <li>点击"新集成"创建集成</li>
              <li>复制"内部集成令牌"</li>
              <li>在Notion页面中邀请该集成</li>
            </ol>
          </div>
        </CardContent>
      </Card>

      {/* 默认配置 */}
      {isConnected && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="w-5 h-5" />
              默认设置
            </CardTitle>
            <CardDescription>
              配置新笔记的默认保存方式和目标位置
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* 默认保存模式 */}
            <div className="space-y-2">
              <Label>默认保存方式</Label>
              <Select 
                value={notionConfig.defaultSaveMode} 
                onValueChange={(value: 'database' | 'standalone') => 
                  setNotionConfig({ defaultSaveMode: value })
                }
              >
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

            {/* 默认数据库选择 */}
            {notionConfig.defaultSaveMode === 'database' && (
              <div className="space-y-2">
                <Label htmlFor="database">默认数据库</Label>
                <div className="flex gap-2">
                  <Select 
                    value={notionConfig.defaultDatabaseId} 
                    onValueChange={(value) => 
                      setNotionConfig({ defaultDatabaseId: value })
                    }
                  >
                    <SelectTrigger className="flex-1">
                      <SelectValue placeholder="选择默认数据库" />
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

            {/* 自动保存开关 */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>自动保存到Notion</Label>
                <p className="text-sm text-muted-foreground">
                  笔记生成完成后自动保存到Notion
                </p>
              </div>
              <Switch
                checked={notionConfig.autoSaveEnabled}
                onCheckedChange={(checked) => 
                  setNotionConfig({ autoSaveEnabled: checked })
                }
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* 批量操作 */}
      {isConnected && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="w-5 h-5" />
              批量操作
            </CardTitle>
            <CardDescription>
              批量管理和同步历史笔记到Notion
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>批量同步未保存的笔记</Label>
                <p className="text-sm text-muted-foreground">
                  将所有未同步到Notion的笔记一键批量同步
                </p>
              </div>
              <BatchNotionSync />
            </div>
            
            <Separator />
            
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>强制批量同步所有笔记</Label>
                <p className="text-sm text-muted-foreground">
                  强制同步所有笔记到Notion，包括已同步的（会创建新页面）
                </p>
              </div>
              <ForceBatchNotionSync />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export default NotionSettings 