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

interface TaskStore {
  tasks: Task[]
  currentTaskId: string | null
  addPendingTask: (taskId: string, platform: string, formData: any) => void
  addPendingTasks: (taskList: Array<{task_id: string, video_url: string, title: string}>, platform: string, formData: any) => void
  updateTaskContent: (id: string, data: Partial<Omit<Task, 'id' | 'createdAt'>>) => void
  removeTask: (id: string) => void
  clearTasks: () => void
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
          currentTaskId: taskId, // 默认设置为当前任务
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

                return {
                  ...task,
                  ...data,
                  markdown: updatedMarkdown,
                }
              }

              return { ...task, ...data }
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
          // 首先调用后端重试接口
          const { retry_task } = await import('@/services/note')
          await retry_task(id)
          
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
          console.error('重试任务失败:', error)
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
    }
  )
)
