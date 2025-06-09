import { useEffect, useRef } from 'react'
import { useTaskStore, type Task } from '@/store/taskStore'
import { useSystemStore } from '@/store/configStore'
import { get_task_status } from '@/services/note.ts'
import { saveNoteToNotion } from '@/services/notion'
import toast from 'react-hot-toast'

export const useTaskPolling = (interval = 3000) => {
  // 获取store实例，而不是使用hooks
  const store = useTaskStore.getState()
  const systemStore = useSystemStore.getState()
  const tasksRef = useRef<Task[]>([])
  const updateTaskContentRef = useRef(store.updateTaskContent)
  const updateTaskNotionRef = useRef(store.updateTaskNotion)
  const notionConfigRef = useRef(systemStore.notionConfig)

  // 监听tasks变化
  useEffect(() => {
    const unsubscribeTask = useTaskStore.subscribe(
      (state) => {
        tasksRef.current = state.tasks
        updateTaskContentRef.current = state.updateTaskContent
        updateTaskNotionRef.current = state.updateTaskNotion
      }
    )
    
    const unsubscribeSystem = useSystemStore.subscribe(
      (state) => {
        notionConfigRef.current = state.notionConfig
      }
    )
    
    // 初始化当前状态
    const currentTaskState = useTaskStore.getState()
    tasksRef.current = currentTaskState.tasks
    updateTaskContentRef.current = currentTaskState.updateTaskContent
    updateTaskNotionRef.current = currentTaskState.updateTaskNotion
    
    const currentSystemState = useSystemStore.getState()
    notionConfigRef.current = currentSystemState.notionConfig

    return () => {
      unsubscribeTask()
      unsubscribeSystem()
    }
  }, [])

  useEffect(() => {
    const timer = setInterval(async () => {
      const pendingTasks: Task[] = tasksRef.current.filter(
        task => task.status !== 'SUCCESS' && task.status !== 'FAILED'
      )

      for (const task of pendingTasks) {
        try {
          console.log('🔄 正在轮询任务：', task.id)
          const res = await get_task_status(task.id)
          const { status } = res.data

          // 只有当状态确实发生变化时才更新
          if (status && status !== task.status) {
            console.log(`📊 任务 ${task.id} 状态变化: ${task.status} -> ${status}`)
            
            if (status === 'SUCCESS') {
              const { markdown, transcript, audio_meta } = res.data.result
              toast.success('笔记生成成功')
              await updateTaskContentRef.current(task.id, {
                status,
                markdown,
                transcript,
                audioMeta: audio_meta,
              })

              // 检查是否需要自动保存到Notion
              if (task.formData.auto_save_notion || notionConfigRef.current.autoSaveEnabled) {
                console.log('🔄 开始自动保存到Notion:', task.id)
                const notionConfig = notionConfigRef.current
                
                if (notionConfig.token) {
                  try {
                    const result = await saveNoteToNotion({
                      taskId: task.id,
                      token: notionConfig.token,
                      databaseId: notionConfig.defaultSaveMode === 'database' ? notionConfig.defaultDatabaseId : undefined
                    })

                    if (result) {
                      await updateTaskNotionRef.current(task.id, {
                        saved: true,
                        pageId: result.page_id,
                        pageUrl: result.url,
                        savedAt: new Date().toISOString(),
                        autoSave: true
                      })
                      console.log('✅ 自动保存到Notion成功:', result.url)
                      toast.success(`笔记已自动保存到Notion`)
                    } else {
                      console.warn('⚠️ 自动保存到Notion失败')
                      toast.error('自动保存到Notion失败，请手动保存')
                    }
                  } catch (error) {
                    console.error('❌ 自动保存到Notion出错:', error)
                    toast.error('自动保存到Notion失败，请手动保存')
                  }
                } else {
                  console.warn('⚠️ 未找到Notion令牌，跳过自动保存')
                  toast.error('未配置Notion令牌，请前往设置页面配置')
                }
              }
            } else if (status === 'FAILED') {
              await updateTaskContentRef.current(task.id, { status })
              console.warn(`⚠️ 任务 ${task.id} 失败`)
            } else {
              // 其他状态变化（如PENDING -> RUNNING）
              await updateTaskContentRef.current(task.id, { status })
            }
          } else {
            console.debug(`⏭️ 任务 ${task.id} 状态无变化 (${task.status})，跳过更新`)
          }
        } catch (e: any) {
          console.error('❌ 任务轮询失败：', e)
          toast.error(`生成失败 ${e.message || e}`)
          await updateTaskContentRef.current(task.id, { status: 'FAILED' })
          // removeTask(task.id)
        }
      }
    }, interval)

    return () => clearInterval(timer)
  }, [interval])
}
