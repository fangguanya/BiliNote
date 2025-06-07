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
import { Loader2, Database, FileText, TestTube, RefreshCw, ExternalLink } from 'lucide-react'
import { toast } from 'sonner'
import { 
  testNotionConnection, 
  getNotionDatabases,
  NotionDatabase 
} from '@/services/notion'
import { useSystemStore } from '@/store/configStore'

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
        <h2 className="text-2xl font-bold tracking-tight">Notion 集成设置</h2>
        <p className="text-muted-foreground">
          配置 Notion 集成，让笔记自动保存到你的 Notion 工作区
        </p>
      </div>

      <Separator />

      {/* 连接配置 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TestTube className="w-5 h-5" />
            连接配置
          </CardTitle>
          <CardDescription>
            配置 Notion 集成令牌，建立与你的 Notion 工作区的连接
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="token">Notion 集成令牌</Label>
            <div className="flex gap-2">
              <Input
                id="token"
                type="password"
                value={tempToken}
                onChange={(e) => setTempToken(e.target.value)}
                placeholder="输入你的 Notion 集成令牌"
                className="flex-1"
              />
              <Button
                onClick={handleTestConnection}
                disabled={isConnecting || !tempToken.trim()}
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
              <p className="text-sm text-green-600 flex items-center gap-2">
                ✅ 已连接到 Notion
              </p>
            )}
            <p className="text-sm text-muted-foreground">
              请确保你的 Notion 集成拥有必要的权限来读取和创建页面
            </p>
          </div>

          <div className="flex gap-2">
            <Button 
              onClick={handleSaveConfig}
              disabled={!tempToken.trim()}
              size="sm"
            >
              保存配置
            </Button>
            <Button 
              onClick={handleClearConfig}
              variant="outline"
              size="sm"
            >
              清除配置
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* 保存设置 */}
      {isConnected && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="w-5 h-5" />
              保存设置
            </CardTitle>
            <CardDescription>
              配置笔记的默认保存方式和目标位置
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
                    未找到数据库，请在 Notion 中创建数据库后重试
                  </p>
                )}
              </div>
            )}

            {/* 自动保存开关 */}
            <div className="flex items-center justify-between space-x-2">
              <div className="space-y-0.5">
                <Label>启用自动保存</Label>
                <p className="text-sm text-muted-foreground">
                  笔记生成完成后自动保存到 Notion
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

      {/* 帮助信息 */}
      <Card>
        <CardHeader>
          <CardTitle>如何获取 Notion 集成令牌？</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-sm text-muted-foreground">
            1. 访问 <Button variant="link" className="h-auto p-0 text-blue-600" onClick={() => window.open('https://www.notion.so/my-integrations', '_blank')}>
              <ExternalLink className="w-3 h-3 mr-1" />
              Notion 集成页面
            </Button>
          </p>
          <p className="text-sm text-muted-foreground">
            2. 点击 "新集成" 创建一个新的集成
          </p>
          <p className="text-sm text-muted-foreground">
            3. 复制生成的 "内部集成令牌"
          </p>
          <p className="text-sm text-muted-foreground">
            4. 在 Notion 中将集成添加到你想要保存笔记的数据库或页面
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

export default NotionSettings 