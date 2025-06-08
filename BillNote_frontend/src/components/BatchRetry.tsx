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
  AlertTriangle,
  CheckCircle,
  Zap
} from 'lucide-react'
import { toast } from 'sonner'
import { batch_retry_non_success_tasks, force_retry_all_tasks, get_task_status, validate_tasks, batch_clear_reset_tasks } from '@/services/note'
import { useTaskStore } from '@/store/taskStore'

interface BatchRetryProps {
  disabled?: boolean
}

const BatchRetry: React.FC<BatchRetryProps> = ({ disabled = false }) => {
  const { tasks, updateTaskContent } = useTaskStore()
  const [isOpen, setIsOpen] = useState(false)
  const [isRetrying, setIsRetrying] = useState(false)
  const [retryStep, setRetryStep] = useState('') // 用于显示当前重试步骤

  // 获取所有非成功的任务
  const nonSuccessTasks = tasks.filter(task => task.status !== 'SUCCESS')
  const pendingTasks = tasks.filter(task => task.status === 'PENDING')
  const runningTasks = tasks.filter(task => task.status === 'RUNNING')
  const failedTasks = tasks.filter(task => task.status === 'FAILED')

  // 批量重试非成功任务
  const handleBatchRetry = async () => {
    if (nonSuccessTasks.length === 0) {
      toast('没有需要重试的未完成任务')
      return
    }

    setIsRetrying(true)
    try {
      // 新增：批量验证前端显示的失败任务是否在后端真实存在
      setRetryStep('正在验证任务状态...')
      console.log('🔍 批量验证前端失败任务在后端的真实状态')
      
      const taskIds = nonSuccessTasks.map(task => task.id)
      const validationResult = await validate_tasks(taskIds)
      
      console.log('📊 任务验证结果:', validationResult)
      
      // 根据验证结果更新前端状态
      const realFailedTasks = []
      for (const result of validationResult.validation_results) {
        const task = nonSuccessTasks.find(t => t.id === result.task_id)
        if (!task) continue
        
        if (result.status === 'SUCCESS') {
          // 任务已成功，需要获取完整结果并更新前端状态
          console.log(`✅ 任务 ${result.task_id} 实际已完成，更新前端状态`)
          try {
            const res = await get_task_status(result.task_id)
            if (res.data.status === 'SUCCESS' && res.data.result) {
              updateTaskContent(result.task_id, { 
                status: 'SUCCESS',
                ...res.data.result
              })
            } else {
              updateTaskContent(result.task_id, { status: 'SUCCESS' })
            }
          } catch (error) {
            console.warn(`⚠️ 获取任务 ${result.task_id} 完整结果失败:`, error)
            updateTaskContent(result.task_id, { status: 'SUCCESS' })
          }
        } else if (result.needs_retry) {
          // 需要重试的任务
          realFailedTasks.push(task)
          // 同步更新前端状态
          if (result.status !== task.status) {
            updateTaskContent(result.task_id, { status: result.status })
          }
        } else if (result.status === 'NOT_FOUND') {
          // 任务不存在，从前端移除
          console.log(`🗑️ 任务 ${result.task_id} 不存在，从前端移除`)
          // 这里可以选择移除任务或标记为失败
          updateTaskContent(result.task_id, { status: 'FAILED' })
        }
      }
      
      if (realFailedTasks.length === 0) {
        toast('所有任务都已完成或不存在，无需重试')
        setIsOpen(false)
        return
      }
      
      console.log(`🔍 验证完成，实际需要重试的任务数: ${realFailedTasks.length}/${validationResult.total_tasks}`)

      // 第一步：尝试普通批量重试
      setRetryStep('正在执行批量重试...')
      console.log('🔄 尝试普通批量重试非成功任务')
      
      try {
        const result = await batch_retry_non_success_tasks()
        
        if (result && result.retried_count > 0) {
          // 普通重试成功
          console.log('✅ 普通批量重试成功:', result)
          
          // 更新前端状态，将重试的任务状态改为PENDING
          realFailedTasks.forEach(task => {
            updateTaskContent(task.id, { status: 'PENDING' })
          })
          
          setIsOpen(false)
          return
        }
      } catch (normalRetryError) {
        console.log('⚠️ 普通批量重试失败，尝试强制重试:', normalRetryError)
        
        // 第二步：普通重试失败，尝试强制重试
        setRetryStep('普通重试失败，正在尝试强制重试...')
        
        try {
          const forceResult = await force_retry_all_tasks()
          
          if (forceResult && forceResult.retried_count > 0) {
            console.log('✅ 强制重试成功:', forceResult)
            
            // 强制重试成功，更新所有任务状态为PENDING
            tasks.forEach(task => {
              updateTaskContent(task.id, { status: 'PENDING' })
            })
            
            toast.success(`强制重试成功！已重试 ${forceResult.retried_count} 个任务`)
            setIsOpen(false)
            return
          }
        } catch (forceRetryError) {
          console.error('❌ 强制重试也失败了:', forceRetryError)
          
          // 第三步：强制重试失败，询问是否清空重置
          setRetryStep('强制重试失败，准备清空重置...')
          
          console.log('⚠️ 强制重试失败，尝试清空重置失败的任务')
          
          try {
            // 获取失败任务的ID列表
            const failedTaskIds = realFailedTasks.map(task => task.id)
            
            const clearResult = await batch_clear_reset_tasks(failedTaskIds, true)
            
            if (clearResult && clearResult.success_count > 0) {
              console.log('✅ 清空重置成功:', clearResult)
              
              // 清空重置成功，更新前端状态为PENDING
              realFailedTasks.forEach(task => {
                updateTaskContent(task.id, { status: 'PENDING' })
              })
              
              toast.success(`清空重置成功！已重新创建 ${clearResult.success_count} 个任务`)
              setIsOpen(false)
              return
            } else {
              console.error('❌ 清空重置也失败了')
              toast.error('所有重试方式都失败了，请手动检查任务状态')
            }
          } catch (clearError) {
            console.error('❌ 清空重置出错:', clearError)
            toast.error('清空重置失败，请手动处理')
          }
          
          throw forceRetryError
        }
      }
      
    } catch (error) {
      console.error('❌ 批量重试过程失败:', error)
      // 不需要再次显示toast，因为在catch块中已经显示了
    } finally {
      setIsRetrying(false)
      setRetryStep('')
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button 
          variant="outline" 
          size="sm"
          disabled={disabled || nonSuccessTasks.length === 0}
          className="flex items-center gap-2"
        >
          <RotateCcw className="w-4 h-4" />
          一键重试
          {nonSuccessTasks.length > 0 && (
            <Badge variant="secondary" className="ml-1">
              {nonSuccessTasks.length}
            </Badge>
          )}
        </Button>
      </DialogTrigger>
      
      <DialogContent className="sm:max-w-[450px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RotateCcw className="w-5 h-5" />
            智能批量重试
          </DialogTitle>
          <DialogDescription>
            重新执行所有未完成任务，失败时会自动尝试强制重试
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 任务统计 */}
          <div className="p-4 bg-muted/50 rounded-lg">
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 text-green-500" />
                  已成功任务：
                </span>
                <Badge variant="outline" className="bg-green-50 text-green-700">
                  {tasks.filter(t => t.status === 'SUCCESS').length} 个
                </Badge>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <RotateCcw className="w-4 h-4 text-blue-500" />
                  未完成任务：
                </span>
                <Badge variant="outline" className="bg-blue-50 text-blue-700">
                  {nonSuccessTasks.length} 个
                </Badge>
              </div>
              
              {/* 详细状态分布 */}
              {nonSuccessTasks.length > 0 && (
                <div className="ml-6 space-y-1 text-xs text-muted-foreground">
                  {pendingTasks.length > 0 && (
                    <div className="flex justify-between">
                      <span>- 排队中 (PENDING)：</span>
                      <span>{pendingTasks.length} 个</span>
                    </div>
                  )}
                  {runningTasks.length > 0 && (
                    <div className="flex justify-between">
                      <span>- 运行中 (RUNNING)：</span>
                      <span>{runningTasks.length} 个</span>
                    </div>
                  )}
                  {failedTasks.length > 0 && (
                    <div className="flex justify-between">
                      <span>- 失败 (FAILED)：</span>
                      <span>{failedTasks.length} 个</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* 重试策略说明 */}
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-blue-500 mt-0.5" />
              <div className="text-sm text-blue-700">
                <p className="font-medium">智能重试策略：</p>
                <div className="mt-1 space-y-1">
                  <p>1. 首先尝试普通批量重试</p>
                  <p>2. 如果失败，自动启用强制重试</p>
                  <p>3. 强制重试失败时，自动清空重置任务</p>
                  <p>4. 清空重置会删除所有相关文件并重新创建任务</p>
                </div>
              </div>
            </div>
          </div>

          {/* 当前重试步骤显示 */}
          {isRetrying && retryStep && (
            <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <div className="flex items-center gap-2 text-sm text-yellow-700">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{retryStep}</span>
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
            disabled={isRetrying || nonSuccessTasks.length === 0}
            className="relative"
          >
            {isRetrying ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                <span>重试中...</span>
              </>
            ) : (
              <>
                <RotateCcw className="w-4 h-4 mr-2" />
                <Zap className="w-3 h-3 absolute -top-1 -right-1 text-orange-500" />
                <span>智能重试 ({nonSuccessTasks.length} 个)</span>
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default BatchRetry 