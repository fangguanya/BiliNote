import { create } from 'zustand'
import { delete_task, generateNote } from '@/services/note.ts'
import { v4 as uuidv4 } from 'uuid'
import * as taskApi from '@/services/task'
import toast from 'react-hot-toast'

export type TaskStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED'

export interface AudioMeta {
  cover_url: string
  duration: number
  file_path: string
  platform: string
  raw_info: any
  title: string
  video_id: string
}

export interface Segment {
  start: number
  end: number
  text: string
}

export interface Transcript {
  full_text: string
  language: string
  raw: any
  segments: Segment[]
}
export interface Markdown {
  ver_id: string
  content: string
  style: string
  model_name: string
  created_at: string
}

export interface Task {
  id: string
  markdown: string|Markdown [] //为了兼容之前的笔记
  transcript: Transcript
  status: TaskStatus
  audioMeta: AudioMeta
  createdAt: string
  platform: string
  notion?: {
    saved: boolean
    pageId?: string
    pageUrl?: string
    savedAt?: string
    autoSave?: boolean
  }
  formData: {
    video_url: string
    link: undefined | boolean
    screenshot: undefined | boolean
    platform: string
    quality: string
    model_name: string
    provider_id: string
    style?: string
    format?: string[]
    extras?: string
    video_understanding?: boolean
    video_interval?: number
    grid_size?: number[]
    max_collection_videos?: number
    auto_save_notion?: boolean
  }
}

interface TaskStore {
  tasks: Task[]
  currentTaskId: string | null
  isLoading: boolean
  isInitialized: boolean
  addPendingTask: (taskId: string, platform: string, formData: any) => Promise<void>
  addPendingTasks: (taskList: Array<{task_id: string, video_url: string, title: string}>, platform: string, formData: any) => Promise<void>
  updateTaskContent: (id: string, data: Partial<Omit<Task, 'id' | 'createdAt'>>) => Promise<void>
  removeTask: (id: string) => Promise<void>
  clearTasks: () => Promise<void>
  setCurrentTask: (taskId: string | null) => void
  getCurrentTask: () => Task | null
  retryTask: (id: string, payload?: any) => void
  updateTaskNotion: (taskId: string, notionData: NonNullable<Task['notion']>) => Promise<void>
  loadTasks: () => Promise<void>
  initializeStore: () => Promise<void>
  migrateFromLocalStorage: () => Promise<void>
}

export const useTaskStore = create<TaskStore>()((set, get) => ({
  tasks: [],
  currentTaskId: null,
  isLoading: false,
  isInitialized: false,

  initializeStore: async () => {
    const state = get()
    if (state.isInitialized) return

    set({ isLoading: true })
    
    try {
      // 检查是否有localStorage数据需要迁移
      await state.migrateFromLocalStorage()
      
      // 加载后端任务数据
      await state.loadTasks()
      
      set({ isInitialized: true })
    } catch (error) {
      console.error('❌ 初始化任务存储失败:', error)
      toast.error('初始化任务数据失败')
    } finally {
      set({ isLoading: false })
    }
  },

  migrateFromLocalStorage: async () => {
    try {
      // 检查localStorage中是否有旧的任务数据
      const localStorageData = localStorage.getItem('task-storage')
      if (!localStorageData) return

      const parsedData = JSON.parse(localStorageData)
      const localTasks = parsedData?.state?.tasks

      if (localTasks && Array.isArray(localTasks) && localTasks.length > 0) {
        // 检查是否刚刚进行过迁移，避免频繁迁移
        const lastMigrationTime = localStorage.getItem('last_migration_time')
        const currentTime = Date.now()
        const migrationInterval = 30000 // 30秒

        if (lastMigrationTime && (currentTime - parseInt(lastMigrationTime)) < migrationInterval) {
          const remainingTime = migrationInterval - (currentTime - parseInt(lastMigrationTime))
          console.log(`⏱️ 迁移请求过于频繁，跳过本次迁移。还需等待 ${Math.ceil(remainingTime / 1000)} 秒`)
          return
        }

        console.log(`🔄 发现 ${localTasks.length} 个本地任务，开始迁移到后端...`)
        
        // 记录迁移时间
        localStorage.setItem('last_migration_time', currentTime.toString())
        
        // 显示迁移进度提示
        const loadingToast = toast.loading(`正在迁移 ${localTasks.length} 个任务...`)
        
        try {
          const result = await taskApi.migrateTasks(localTasks)
          console.log('✅ 任务迁移响应:', result)
          
          // 关闭loading提示
          toast.dismiss(loadingToast)
          
          // 检查是否被限流
          if (result.rate_limited) {
            console.log('⏱️ 迁移被限流，但本地数据保留')
            toast('迁移请求过于频繁，请稍后自动重试', { icon: 'ℹ️' })
            return
          }
          
          // 迁移完成后删除localStorage数据（无论是新增还是更新）
          localStorage.removeItem('task-storage')
          localStorage.removeItem('last_migration_time') // 清除限流记录
          
          if (result.migrated_count > 0) {
            toast.success(`成功迁移 ${result.migrated_count} 个任务到后端存储`)
          } else {
            // 即使没有新增任务，也可能更新了现有任务
            toast.success(`任务数据已同步到后端存储`)
          }
          
          if (result.failed_tasks && result.failed_tasks.length > 0) {
            console.warn('⚠️ 部分任务迁移失败:', result.failed_tasks)
            toast.error(`${result.failed_tasks.length} 个任务迁移失败，请检查后端服务`)
          }
        } catch (error: any) {
          // 关闭loading提示
          toast.dismiss(loadingToast)
          
          console.error('❌ 任务迁移失败:', error)
          
          // 迁移失败时清除限流记录，允许下次重试
          localStorage.removeItem('last_migration_time')
          
          // 根据错误类型提供不同的提示
          if (error.code === 'ERR_NETWORK' || error.code === 'ERR_BAD_REQUEST') {
            if (error.message.includes('localhost:1988')) {
              toast.error('后端服务连接失败，请确保后端服务正在运行在8000端口')
            } else {
              toast.error('网络连接失败，请检查后端服务是否启动')
            }
          } else if (error.response?.status === 400) {
            console.error('❌ 请求数据格式错误:', error.response?.data)
            toast.error('数据格式错误，请联系开发者')
          } else if (error.response?.status === 500) {
            console.error('❌ 后端服务器错误:', error.response?.data)
            toast.error('后端服务器错误，请检查后端日志')
          } else {
            toast.error('任务迁移失败，请稍后重试或联系开发者')
          }
        }
      }
    } catch (error) {
      console.error('❌ 检查本地存储失败:', error)
      toast.error('读取本地存储失败')
    }
  },

  loadTasks: async () => {
    try {
      set({ isLoading: true })
      const response = await taskApi.getTasks({ limit: 1000 })
      set({ 
        tasks: response.tasks,
        currentTaskId: response.currentTaskId || null
      })
      
      // 验证文件数据完整性
      try {
        await taskApi.validateFilesIntegrity()
      } catch (validationError) {
        console.warn('⚠️ 文件完整性验证失败，但不影响任务加载:', validationError)
      }
      
    } catch (error) {
      console.error('❌ 加载任务失败:', error)
      toast.error('加载任务数据失败')
    } finally {
      set({ isLoading: false })
    }
  },

  addPendingTask: async (taskId: string, platform: string, formData: any) => {
    try {
      // 先在前端添加任务（优化用户体验）
      const newTask: Task = {
        formData: formData,
        id: taskId,
        status: 'PENDING',
        markdown: '',
        platform: platform,
        transcript: {
          full_text: '',
          language: '',
          raw: null,
          segments: [],
        },
        createdAt: new Date().toISOString(),
        audioMeta: {
          cover_url: '',
          duration: 0,
          file_path: '',
          platform: '',
          raw_info: null,
          title: '',
          video_id: '',
        },
      }

      set(state => ({
        tasks: [newTask, ...state.tasks],
        currentTaskId: taskId,
      }))

      // 创建后端任务
      await taskApi.createTask({
        id: taskId,
        platform: platform,
        formData: formData
      })

    } catch (error) {
      console.error('❌ 创建任务失败:', error)
      // 回滚前端状态
      set(state => ({
        tasks: state.tasks.filter(t => t.id !== taskId),
        currentTaskId: state.currentTaskId === taskId ? null : state.currentTaskId
      }))
      toast.error('创建任务失败')
      throw error
    }
  },

  addPendingTasks: async (taskList: Array<{task_id: string, video_url: string, title: string}>, platform: string, formData: any) => {
    try {
      const newTasks = taskList.map(({ task_id, video_url, title }) => ({
        formData: {
          ...formData,
          video_url: video_url
        },
        id: task_id,
        status: 'PENDING' as TaskStatus,
        markdown: '',
        platform: platform,
        transcript: {
          full_text: '',
          language: '',
          raw: null,
          segments: [],
        },
        createdAt: new Date().toISOString(),
        audioMeta: {
          cover_url: '',
          duration: 0,
          file_path: '',
          platform: platform,
          raw_info: null,
          title: title || '未知标题',
          video_id: '',
        },
      }))

      // 先更新前端状态
      set(state => ({
        tasks: [...newTasks, ...state.tasks],
        currentTaskId: taskList.length > 0 ? taskList[0].task_id : state.currentTaskId,
      }))

      // 批量创建后端任务
      const createTasks = taskList.map(({ task_id, video_url }) => ({
        id: task_id,
        platform: platform,
        formData: {
          ...formData,
          video_url: video_url
        }
      }))

      await taskApi.createBatchTasks(createTasks)

    } catch (error) {
      console.error('❌ 批量创建任务失败:', error)
      // 回滚前端状态
      const taskIds = taskList.map(t => t.task_id)
      set(state => ({
        tasks: state.tasks.filter(t => !taskIds.includes(t.id))
      }))
      toast.error('批量创建任务失败')
      throw error
    }
  },

  updateTaskContent: async (id, data) => {
    try {
      // 获取当前任务，判断是否需要更新
      const currentTask = get().tasks.find(task => task.id === id)
      if (!currentTask) {
        console.warn(`⚠️ 任务 ${id} 不存在，无法更新`)
        return
      }

      // 检查是否有实际变化，避免无意义的更新
      let hasChanges = false
      const changes: string[] = []

      if (data.status && data.status !== currentTask.status) {
        hasChanges = true
        changes.push(`状态: ${currentTask.status} -> ${data.status}`)
      }

      if (data.markdown && data.markdown !== currentTask.markdown) {
        hasChanges = true
        changes.push('markdown内容已变化')
      }

      if (data.transcript && JSON.stringify(data.transcript) !== JSON.stringify(currentTask.transcript)) {
        hasChanges = true
        changes.push('转录内容已变化')
      }

      if (data.audioMeta && JSON.stringify(data.audioMeta) !== JSON.stringify(currentTask.audioMeta)) {
        hasChanges = true
        changes.push('音频元数据已变化')
      }

      if (data.notion && JSON.stringify(data.notion) !== JSON.stringify(currentTask.notion)) {
        hasChanges = true
        changes.push('Notion信息已变化')
      }

      // 如果没有实际变化，跳过更新
      if (!hasChanges) {
        console.debug(`⏭️ 任务 ${id} 数据无变化，跳过更新`)
        return
      }

      console.log(`🔄 更新任务 ${id}: ${changes.join(', ')}`)

      // 先更新前端状态（优化用户体验）
      set(state => ({
        tasks: state.tasks.map(task => {
          if (task.id !== id) return task

          if (task.status === 'SUCCESS' && data.status === 'SUCCESS') return task

          // 如果是 markdown 字符串，封装为版本
          if (typeof data.markdown === 'string') {
            const prev = task.markdown
            const newVersion: Markdown = {
              ver_id: `${task.id}-${uuidv4()}`,
              content: data.markdown,
              style: task.formData.style || '',
              model_name: task.formData.model_name || '',
              created_at: new Date().toISOString(),
            }

            let updatedMarkdown: Markdown[]
            if (Array.isArray(prev)) {
              updatedMarkdown = [newVersion, ...prev]
            } else {
              updatedMarkdown = [
                newVersion,
                ...(typeof prev === 'string' && prev
                    ? [{
                      ver_id: `${task.id}-${uuidv4()}`,
                      content: prev,
                      style: task.formData.style || '',
                      model_name: task.formData.model_name || '',
                      created_at: new Date().toISOString(),
                    }]
                    : []),
              ]
            }

            return {
              ...task,
              ...data,
              markdown: updatedMarkdown,
            }
          }

          return { ...task, ...data }
        }),
      }))

      // 更新后端任务（只有存在实际变化时才调用）
      await taskApi.updateTask(id, {
        status: data.status,
        markdown: data.markdown,
        transcript: data.transcript,
        audioMeta: data.audioMeta,
        notion: data.notion
      })

    } catch (error) {
      console.error('❌ 更新任务失败:', error)
      // 可以选择重新加载任务来恢复状态
      // await get().loadTasks()
      throw error
    }
  },

  getCurrentTask: () => {
    const currentTaskId = get().currentTaskId
    return get().tasks.find(task => task.id === currentTaskId) || null
  },

  retryTask: async (id: string, payload?: any) => {
    const task = get().tasks.find(task => task.id === id)
    if (!task) return

    try {
      // 首先尝试普通重试接口
      const { retry_task, force_retry_task } = await import('@/services/note')
      
      try {
        await retry_task(id)
        console.log('✅ 普通重试成功:', id)
      } catch (error) {
        console.log('⚠️ 普通重试失败，尝试强制重试:', error)
        // 普通重试失败，尝试强制重试
        await force_retry_task(id)
      }
      
      // 重试成功，更新前端状态
      set(state => ({
        tasks: state.tasks.map(t =>
            t.id === id
                ? {
                  ...t,
                  formData: payload || t.formData, // 如果有新的formData则更新
                  status: 'PENDING',
                }
                : t
        ),
      }))

      // 更新后端状态
      await taskApi.updateTask(id, {
        status: 'PENDING',
      })

    } catch (error) {
      console.error('🔥 重试任务失败:', error)
      // 重试失败，保持原状态或者可以显示错误信息
    }
  },

  removeTask: async id => {
    try {
      const task = get().tasks.find(t => t.id === id)

      // 更新前端状态
      set(state => ({
        tasks: state.tasks.filter(task => task.id !== id),
        currentTaskId: state.currentTaskId === id ? null : state.currentTaskId,
      }))

      // 删除后端任务
      await taskApi.deleteTask(id)

      // 调用原有的删除接口（如果找到了任务）
      if (task) {
        await delete_task({
          video_id: task.audioMeta.video_id,
          platform: task.platform,
        })
      }

    } catch (error) {
      console.error('❌ 删除任务失败:', error)
      // 可以选择重新加载任务来恢复状态
      await get().loadTasks()
      toast.error('删除任务失败')
    }
  },

  clearTasks: async () => {
    try {
      // 获取所有任务ID
      const taskIds = get().tasks.map(t => t.id)
      
      // 清空前端状态
      set({ tasks: [], currentTaskId: null })

      // 批量删除后端任务
      for (const taskId of taskIds) {
        try {
          await taskApi.deleteTask(taskId)
        } catch (error) {
          console.error(`❌ 删除任务 ${taskId} 失败:`, error)
        }
      }

    } catch (error) {
      console.error('❌ 清空任务失败:', error)
      toast.error('清空任务失败')
    }
  },

  setCurrentTask: taskId => {
    const currentTaskId = get().currentTaskId
    if (currentTaskId === taskId) {
      // 如果设置的任务ID与当前任务ID相同，跳过更新
      return
    }
    console.log(`📍 切换当前任务: ${currentTaskId} -> ${taskId}`)
    set({ currentTaskId: taskId })
  },

  updateTaskNotion: async (taskId: string, notionData: NonNullable<Task['notion']>) => {
    try {
      const currentTask = get().tasks.find(task => task.id === taskId)
      if (!currentTask) {
        console.warn(`⚠️ 任务 ${taskId} 不存在，无法更新Notion信息`)
        return
      }

      // 检查Notion信息是否真的有变化
      const currentNotionStr = JSON.stringify(currentTask.notion || {})
      const newNotionStr = JSON.stringify(notionData)
      
      if (currentNotionStr === newNotionStr) {
        console.debug(`⏭️ 任务 ${taskId} 的Notion信息无变化，跳过更新`)
        return
      }

      console.log(`🔄 更新任务 ${taskId} 的Notion信息`)

      // 更新前端状态
      set(state => ({
        tasks: state.tasks.map(task =>
          task.id === taskId
            ? { ...task, notion: notionData }
            : task
        )
      }))

      // 更新后端
      await taskApi.updateTask(taskId, {
        notion: notionData
      })

    } catch (error) {
      console.error('❌ 更新Notion信息失败:', error)
      // 可以选择重新加载任务来恢复状态
      await get().loadTasks()
      throw error
    }
  },
}))

// 自动初始化store
useTaskStore.getState().initializeStore()
