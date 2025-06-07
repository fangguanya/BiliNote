import React, { useState } from 'react'
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
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { 
  Loader2, 
  Zap,
  AlertTriangle
} from 'lucide-react'
import { toast } from 'sonner'
import { force_retry_all_tasks } from '@/services/note'
import { useTaskStore } from '@/store/taskStore'
import { useModelStore } from '@/store/modelStore'

interface ForceRetryAllProps {
  disabled?: boolean
}

const ForceRetryAll: React.FC<ForceRetryAllProps> = ({ disabled = false }) => {
  const { tasks, updateTaskContent } = useTaskStore()
  const { modelList } = useModelStore()
  const [isOpen, setIsOpen] = useState(false)
  const [isRetrying, setIsRetrying] = useState(false)
  
  // 配置状态
  const [useNewConfig, setUseNewConfig] = useState(false)
  const [selectedModel, setSelectedModel] = useState('')
  const [selectedStyle, setSelectedStyle] = useState('')
  const [videoUnderstanding, setVideoUnderstanding] = useState(false)
  const [videoInterval, setVideoInterval] = useState(4)

  // 获取所有任务
  const allTasks = tasks.filter(task => task.status === 'SUCCESS' || task.status === 'FAILED')

  // 强制重试所有任务
  const handleForceRetry = async () => {
    if (allTasks.length === 0) {
      toast('没有任务可以重试')
      return
    }

    setIsRetrying(true)
    try {
      let config = undefined
      if (useNewConfig) {
        const selectedModelData = modelList.find(m => m.model_name === selectedModel)
        config = {
          model_name: selectedModel || undefined,
          provider_id: selectedModelData?.provider_id || undefined,
          style: selectedStyle || undefined,
          video_understanding: videoUnderstanding,
          video_interval: videoInterval
        }
      }

      const result = await force_retry_all_tasks(config)
      
      if (result && result.retried_count > 0) {
        // 更新前端状态，将所有重试的任务状态改为PENDING
        allTasks.forEach(task => {
          updateTaskContent(task.id, { status: 'PENDING' })
        })
        
        setIsOpen(false)
      }
    } catch (error) {
      console.error('强制重试失败:', error)
    } finally {
      setIsRetrying(false)
    }
  }

  const noteStyles = [
    { value: 'academic', label: '学术风格' },
    { value: 'business', label: '商务风格' },
    { value: 'casual', label: '轻松风格' },
    { value: 'detailed', label: '详细风格' },
    { value: 'concise', label: '简洁风格' }
  ]

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button 
          variant="secondary" 
          size="sm"
          disabled={disabled || allTasks.length === 0}
          className="flex items-center gap-2 border-orange-200 bg-orange-50 hover:bg-orange-100 text-orange-700"
        >
          <Zap className="w-4 h-4" />
          强制重试
          {allTasks.length > 0 && (
            <Badge variant="secondary" className="ml-1 bg-orange-200 text-orange-700">
              {allTasks.length}
            </Badge>
          )}
        </Button>
      </DialogTrigger>
      
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-orange-500" />
            强制重试所有任务
          </DialogTitle>
          <DialogDescription>
            使用最新配置重新生成所有笔记，包括已成功的任务
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 警告提示 */}
          <div className="p-3 bg-orange-50 border border-orange-200 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-orange-500 mt-0.5" />
              <div className="text-sm text-orange-700">
                <p className="font-medium">注意：</p>
                <p>此操作将重新生成所有笔记，包括已成功的任务。所有任务将重新进入队列。</p>
              </div>
            </div>
          </div>

          {/* 重试统计 */}
          <div className="p-4 bg-muted/50 rounded-lg">
            <div className="flex items-center justify-between text-sm">
              <span>可重试任务总数：</span>
              <Badge variant="outline">{allTasks.length} 个</Badge>
            </div>
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-muted-foreground">
                （成功: {tasks.filter(t => t.status === 'SUCCESS').length} 个，失败: {tasks.filter(t => t.status === 'FAILED').length} 个）
              </span>
            </div>
          </div>

          {/* 配置选项 */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="use-new-config">使用新配置</Label>
              <Switch
                id="use-new-config"
                checked={useNewConfig}
                onCheckedChange={setUseNewConfig}
              />
            </div>

            {useNewConfig && (
              <div className="space-y-3 p-3 border rounded-lg bg-muted/30">
                {/* 模型选择 */}
                <div className="space-y-2">
                  <Label>AI模型</Label>
                  <Select value={selectedModel} onValueChange={setSelectedModel}>
                    <SelectTrigger>
                      <SelectValue placeholder="选择模型（留空保持原配置）" />
                    </SelectTrigger>
                    <SelectContent>
                      {modelList.map((model) => (
                        <SelectItem key={model.model_name} value={model.model_name}>
                          {model.model_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* 风格选择 */}
                <div className="space-y-2">
                  <Label>笔记风格</Label>
                  <Select value={selectedStyle} onValueChange={setSelectedStyle}>
                    <SelectTrigger>
                      <SelectValue placeholder="选择风格（留空保持原配置）" />
                    </SelectTrigger>
                    <SelectContent>
                      {noteStyles.map((style) => (
                        <SelectItem key={style.value} value={style.value}>
                          {style.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* 视频理解 */}
                <div className="flex items-center justify-between">
                  <Label htmlFor="video-understanding">视频内容理解</Label>
                  <Switch
                    id="video-understanding"
                    checked={videoUnderstanding}
                    onCheckedChange={setVideoUnderstanding}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button 
            variant="outline" 
            onClick={() => setIsOpen(false)}
            disabled={isRetrying}
          >
            取消
          </Button>
          <Button 
            onClick={handleForceRetry}
            disabled={isRetrying || allTasks.length === 0}
            className="bg-orange-500 hover:bg-orange-600"
          >
            {isRetrying ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <Zap className="w-4 h-4 mr-2" />
            )}
            {isRetrying ? '重试中...' : `开始强制重试 (${allTasks.length} 个)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ForceRetryAll 