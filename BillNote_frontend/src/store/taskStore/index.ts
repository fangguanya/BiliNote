import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { delete_task, generateNote } from '@/services/note.ts'
import { v4 as uuidv4 } from 'uuid'


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

// 辅助函数：精简任务数据以减少存储空间
// 策略：
// 1. 只保留 transcript.full_text，删除 segments（segments 数据量很大）
// 2. 只保留 markdown 文本，如果是数组则只保留第一个
// 3. 删除 raw_info 等大型对象
const compactTask = (task: Task): Task => {
  return {
    ...task,
    // 精简 transcript：只保留 full_text，删除 segments
    transcript: {
      full_text: task.transcript?.full_text || '',
      language: task.transcript?.language || '',
      raw: null, // 删除原始数据
      segments: [], // 删除分段数据（占用空间最大）
    },
    // 精简 markdown：如果是数组，只保留第一个
    markdown: Array.isArray(task.markdown) 
      ? (task.markdown.length > 0 ? task.markdown[0].content : '')
      : task.markdown,
    // 精简 audioMeta：删除 raw_info
    audioMeta: {
      ...task.audioMeta,
      raw_info: null, // 删除原始信息
    }
  }
}

// 辅助函数：批量精简任务
const compactTasks = (tasks: Task[]): Task[] => {
  return tasks.map(compactTask)
}

interface TaskStore {
  tasks: Task[]
  currentTaskId: string | null
  addPendingTask: (taskId: string, platform: string, formData: any) => void
  addPendingTasks: (taskList: Array<{task_id: string, video_url: string, title: string}>, platform: string, formData: any) => void
  updateTaskContent: (id: string, data: Partial<Omit<Task, 'id' | 'createdAt'>>) => void
  removeTask: (id: string) => void
  clearTasks: () => void
  compactAllTasks: () => void // 新增：手动精简所有任务数据
  setCurrentTask: (taskId: string | null) => void
  getCurrentTask: () => Task | null
  retryTask: (id: string, payload?: any) => void
  updateTaskNotion: (taskId: string, notionData: NonNullable<Task['notion']>) => void
}

export const useTaskStore = create<TaskStore>()(
  persist(
    (set, get) => ({
      tasks: [],
      currentTaskId: null,

      addPendingTask: (taskId: string, platform: string, formData: any) =>

        set(state => ({
          tasks: [
            {
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
            },
            ...state.tasks,
          ],
          currentTaskId: taskId,
        })),

      addPendingTasks: (taskList: Array<{task_id: string, video_url: string, title: string}>, platform: string, formData: any) =>
        set(state => {
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

          return {
            tasks: [...newTasks, ...state.tasks],
            currentTaskId: taskList.length > 0 ? taskList[0].task_id : state.currentTaskId,
          }
        }),

      updateTaskContent: (id, data) =>
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

                const updatedTask = {
                  ...task,
                  ...data,
                  markdown: updatedMarkdown,
                }
                
                // 如果任务完成，精简数据以节省存储空间
                if (data.status === 'SUCCESS') {
                  return compactTask(updatedTask)
                }
                
                return updatedTask
              }

              const updatedTask = { ...task, ...data }
              
              // 如果任务完成，精简数据以节省存储空间
              if (data.status === 'SUCCESS') {
                return compactTask(updatedTask)
              }
              
              return updatedTask
            }),
          })),


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
        } catch (error) {
          console.error('🔥 重试任务失败:', error)
          // 重试失败，保持原状态或者可以显示错误信息
        }
      },


      removeTask: async id => {
        const task = get().tasks.find(t => t.id === id)

        // 更新 Zustand 状态
        set(state => ({
          tasks: state.tasks.filter(task => task.id !== id),
          currentTaskId: state.currentTaskId === id ? null : state.currentTaskId,
        }))

        // 调用后端删除接口（如果找到了任务）
        if (task) {
          await delete_task({
            video_id: task.audioMeta.video_id,
            platform: task.platform,
          })
        }
      },

      clearTasks: () => set({ tasks: [], currentTaskId: null }),

      compactAllTasks: () => 
        set(state => {
          const compactedTasks = compactTasks(state.tasks)
          const savedBytes = JSON.stringify(state.tasks).length - JSON.stringify(compactedTasks).length
          console.log(`🗜️ 精简所有任务数据完成，节省 ${(savedBytes / 1024).toFixed(2)} KB`)
          return { tasks: compactedTasks }
        }),

      setCurrentTask: taskId => set({ currentTaskId: taskId }),

      updateTaskNotion: (taskId: string, notionData: NonNullable<Task['notion']>) =>
        set(state => ({
          tasks: state.tasks.map(task =>
            task.id === taskId
              ? { ...task, notion: notionData }
              : task
          )
        })),
    }),
    {
      name: 'task-storage',
      // 添加存储错误处理
      onRehydrateStorage: () => (state) => {
        if (state) {
          const sizeKB = (JSON.stringify(state.tasks).length / 1024).toFixed(2)
          console.log(`📦 任务存储已加载: ${sizeKB} KB, ${state.tasks.length} 个任务`)
          
          // 如果存储过大（超过4MB），自动精简
          if (JSON.stringify(state.tasks).length > 4 * 1024 * 1024) {
            console.warn('⚠️ 任务存储过大，自动精简...')
            const compactedTasks = compactTasks(state.tasks)
            state.tasks = compactedTasks
            const newSize = (JSON.stringify(state.tasks).length / 1024).toFixed(2)
            console.log(`✅ 精简完成: ${newSize} KB`)
          }
        }
      },
      // 添加存储错误处理
      storage: {
        getItem: (name) => {
          const value = localStorage.getItem(name)
          return value ? JSON.parse(value) : null
        },
        setItem: (name, value) => {
          try {
            localStorage.setItem(name, JSON.stringify(value))
          } catch (error) {
            // localStorage 配额超限
            if (error instanceof DOMException && error.name === 'QuotaExceededError') {
              console.error('❌ localStorage 配额超限，尝试自动清理...')
              
              // 尝试精简任务数据
              if (value?.state?.tasks) {
                const compactedTasks = compactTasks(value.state.tasks)
                const compactedValue = {
                  ...value,
                  state: {
                    ...value.state,
                    tasks: compactedTasks
                  }
                }
                
                try {
                  localStorage.setItem(name, JSON.stringify(compactedValue))
                  console.log('✅ 自动精简成功，数据已保存')
                  
                  // 显示用户友好的提示
                  const event = new CustomEvent('storage-quota-exceeded', {
                    detail: { 
                      message: '存储空间不足，已自动精简任务数据。建议定期清理旧任务。',
                      autoFixed: true
                    }
                  })
                  window.dispatchEvent(event)
                  
                  return
                } catch (retryError) {
                  console.error('❌ 精简后仍然超限')
                }
              }
              
              // 如果精简后还是失败，显示错误提示
              const event = new CustomEvent('storage-quota-exceeded', {
                detail: { 
                  message: '存储空间不足！请在控制台运行 useTaskStore.getState().clearTasks() 清理任务，或删除部分旧任务。',
                  autoFixed: false
                }
              })
              window.dispatchEvent(event)
              
              throw error
            } else {
              throw error
            }
          }
        },
        removeItem: (name) => {
          localStorage.removeItem(name)
        },
      },
    }
  )
)
