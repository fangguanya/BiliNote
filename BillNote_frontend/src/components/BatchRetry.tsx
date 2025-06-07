import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogFooter, 
  DialogHeader, 
  DialogTitle, 
  DialogTrigger 
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { 
  Loader2, 
  RotateCcw,
  AlertTriangle
} from 'lucide-react'
import { toast } from 'sonner'
import { batch_retry_failed_tasks } from '@/services/note'
import { useTaskStore } from '@/store/taskStore'

interface BatchRetryProps {
  disabled?: boolean
}

const BatchRetry: React.FC<BatchRetryProps> = ({ disabled = false }) => {
  const { tasks, updateTaskContent } = useTaskStore()
  const [isOpen, setIsOpen] = useState(false)
  const [isRetrying, setIsRetrying] = useState(false)

  // 获取所有失败的任务
  const failedTasks = tasks.filter(task => task.status === 'FAILED')

  // 批量重试失败任务
  const handleBatchRetry = async () => {
    if (failedTasks.length === 0) {
      toast('没有需要重试的失败任务')
      return
    }

    setIsRetrying(true)
    try {
      const result = await batch_retry_failed_tasks()
      
      if (result && result.retried_count > 0) {
        // 更新前端状态，将重试的任务状态改为PENDING
        failedTasks.forEach(task => {
          updateTaskContent(task.id, { status: 'PENDING' })
        })
        
        setIsOpen(false)
      }
    } catch (error) {
      console.error('批量重试失败:', error)
    } finally {
      setIsRetrying(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button 
          variant="outline" 
          size="sm"
          disabled={disabled || failedTasks.length === 0}
          className="flex items-center gap-2"
        >
          <RotateCcw className="w-4 h-4" />
          一键重试
          {failedTasks.length > 0 && (
            <Badge variant="destructive" className="ml-1">
              {failedTasks.length}
            </Badge>
          )}
        </Button>
      </DialogTrigger>
      
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RotateCcw className="w-5 h-5" />
            批量重试失败任务
          </DialogTitle>
          <DialogDescription>
            重新执行所有失败的笔记生成任务
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 重试统计 */}
          <div className="p-4 bg-muted/50 rounded-lg">
            <div className="flex items-center justify-between text-sm">
              <span>失败任务数量：</span>
              <Badge variant="destructive">{failedTasks.length} 个</Badge>
            </div>
          </div>

          {failedTasks.length > 0 && (
            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-blue-500 mt-0.5" />
                <div className="text-sm text-blue-700">
                  <p className="font-medium">注意：</p>
                  <p>此操作将重新执行所有失败的任务，任务将重新进入队列等待处理。</p>
                </div>
              </div>
            </div>
          )}
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
            onClick={handleBatchRetry}
            disabled={isRetrying || failedTasks.length === 0}
          >
            {isRetrying ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <RotateCcw className="w-4 h-4 mr-2" />
            )}
            {isRetrying ? '重试中...' : `开始重试 (${failedTasks.length} 个)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default BatchRetry 