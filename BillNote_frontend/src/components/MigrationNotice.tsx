import React, { useState, useEffect } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { CheckCircle2, AlertCircle, X } from 'lucide-react'
import { useTaskStore } from '@/store/taskStore'

const MigrationNotice: React.FC = () => {
  const [showNotice, setShowNotice] = useState(false)
  const [migrationStatus, setMigrationStatus] = useState<'checking' | 'completed' | 'none'>('checking')
  const isInitialized = useTaskStore(state => state.isInitialized)

  useEffect(() => {
    const checkMigrationStatus = () => {
      // 检查是否需要显示迁移通知
      const hasOldData = localStorage.getItem('task-storage')
      const hasSeenNotice = localStorage.getItem('migration-notice-seen')

      if (hasOldData && !hasSeenNotice) {
        setShowNotice(true)
        setMigrationStatus('checking')
      } else if (hasSeenNotice === 'migrated') {
        setMigrationStatus('completed')
      } else {
        setMigrationStatus('none')
      }
    }

    // 在store初始化后检查
    if (isInitialized) {
      checkMigrationStatus()
    }
  }, [isInitialized])

  const handleDismiss = () => {
    setShowNotice(false)
    localStorage.setItem('migration-notice-seen', 'dismissed')
  }

  const handleMigrationCompleted = () => {
    setMigrationStatus('completed')
    setShowNotice(false)
    localStorage.setItem('migration-notice-seen', 'migrated')
  }

  // 监听localStorage变化，检测迁移完成
  useEffect(() => {
    const handleStorageChange = () => {
      const hasOldData = localStorage.getItem('task-storage')
      if (!hasOldData && migrationStatus === 'checking') {
        handleMigrationCompleted()
      }
    }

    window.addEventListener('storage', handleStorageChange)
    
    // 也定期检查localStorage状态
    const interval = setInterval(handleStorageChange, 1000)

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      clearInterval(interval)
    }
  }, [migrationStatus])

  if (!showNotice && migrationStatus !== 'completed') {
    return null
  }

  return (
    <>
      {showNotice && (
        <Alert className="mb-4 border-blue-200 bg-blue-50">
          <AlertCircle className="h-4 w-4 text-blue-600" />
          <div className="flex items-center justify-between">
            <AlertDescription className="text-blue-800">
              🔄 正在将您的任务数据从本地存储迁移到服务器，这将提供更好的性能和稳定性...
            </AlertDescription>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDismiss}
              className="h-auto p-1 text-blue-600 hover:text-blue-800"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </Alert>
      )}

      {migrationStatus === 'completed' && (
        <Alert className="mb-4 border-green-200 bg-green-50">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <div className="flex items-center justify-between">
            <AlertDescription className="text-green-800">
              ✅ 数据迁移完成！您的任务现在存储在服务器上，享受更好的使用体验。
            </AlertDescription>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setMigrationStatus('none')}
              className="h-auto p-1 text-green-600 hover:text-green-800"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </Alert>
      )}
    </>
  )
}

export default MigrationNotice 