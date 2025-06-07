import { useEffect, useRef } from 'react'
import { useTaskStore, type Task } from '@/store/taskStore'
import { get_task_status } from '@/services/note.ts'
import { saveNoteToNotion } from '@/services/notion'
import toast from 'react-hot-toast'

export const useTaskPolling = (interval = 3000) => {
  // 获取store实例，而不是使用hooks
  const store = useTaskStore.getState()
  const tasksRef = useRef<Task[]>([])
  const updateTaskContentRef = useRef(store.updateTaskContent)
  const updateTaskNotionRef = useRef(store.updateTaskNotion)

  // 监听tasks变化
  useEffect(() => {
    const unsubscribe = useTaskStore.subscribe(
      (state) => {
        tasksRef.current = state.tasks
        updateTaskContentRef.current = state.updateTaskContent
        updateTaskNotionRef.current = state.updateTaskNotion
      }
    )
    
    // 初始化当前状态
    const currentState = useTaskStore.getState()
    tasksRef.current = currentState.tasks
    updateTaskContentRef.current = currentState.updateTaskContent
    updateTaskNotionRef.current = currentState.updateTaskNotion

    return unsubscribe
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

          if (status && status !== task.status) {
            if (status === 'SUCCESS') {
              const { markdown, transcript, audio_meta } = res.data.result
              toast.success('笔记生成成功')
              updateTaskContentRef.current(task.id, {
                status,
                markdown,
                transcript,
                audioMeta: audio_meta,
              })

              // 检查是否需要自动保存到Notion
              if (task.formData.auto_save_notion) {
                console.log('🔄 开始自动保存到Notion:', task.id)
                const savedToken = localStorage.getItem('notion_token')
                
                if (savedToken) {
                  try {
                    const result = await saveNoteToNotion({
                      taskId: task.id,
                      token: savedToken,
                      // 可以考虑从localStorage获取默认数据库ID
                    })

                    if (result) {
                      updateTaskNotionRef.current(task.id, {
                        saved: true,
                        pageId: result.page_id,
                        pageUrl: result.url,
                        savedAt: new Date().toISOString(),
                        autoSave: true
                      })
                      console.log('✅ 自动保存到Notion成功:', result.url)
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
                  toast.error('未配置Notion令牌，跳过自动保存')
                }
              }
            } else if (status === 'FAILED') {
              updateTaskContentRef.current(task.id, { status })
              console.warn(`⚠️ 任务 ${task.id} 失败`)
            } else {
              updateTaskContentRef.current(task.id, { status })
            }
          }
        } catch (e: any) {
          console.error('❌ 任务轮询失败：', e)
          toast.error(`生成失败 ${e.message || e}`)
          updateTaskContentRef.current(task.id, { status: 'FAILED' })
          // removeTask(task.id)
        }
      }
    }, interval)

    return () => clearInterval(timer)
  }, [interval])
}
