import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface NotionConfig {
  token: string
  defaultDatabaseId: string
  defaultSaveMode: 'database' | 'standalone'
  autoSaveEnabled: boolean
}

interface SystemState {
  showFeatureHint: boolean // ✅ 是否显示功能提示
  setShowFeatureHint: (value: boolean) => void

  // 后续如果有其他全局状态，可以继续加
  sidebarCollapsed: boolean // ✅ 侧边栏是否收起
  setSidebarCollapsed: (value: boolean) => void

  // Notion配置
  notionConfig: NotionConfig
  setNotionConfig: (config: Partial<NotionConfig>) => void
  resetNotionConfig: () => void
}

const defaultNotionConfig: NotionConfig = {
  token: '',
  defaultDatabaseId: '',
  defaultSaveMode: 'database',
  autoSaveEnabled: false
}

// 暂不启用
export const useSystemStore = create<SystemState>()(
  persist(
    set => ({
      showFeatureHint: true,
      setShowFeatureHint: value => set({ showFeatureHint: value }),

      sidebarCollapsed: false,
      setSidebarCollapsed: value => set({ sidebarCollapsed: value }),

      notionConfig: defaultNotionConfig,
      setNotionConfig: config => 
        set(state => ({
          notionConfig: { ...state.notionConfig, ...config }
        })),
      resetNotionConfig: () => 
        set({ notionConfig: defaultNotionConfig }),
    }),
    {
      name: 'system-store', // 本地存储的 key
    }
  )
)
