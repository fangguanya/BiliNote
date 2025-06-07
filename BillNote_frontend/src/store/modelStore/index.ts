import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { fetchModels, addModel, fetchEnableModels, fetchEnableModelById, deleteModelById } from '@/services/model.ts'

interface IModel {
  id: string
  created: number
  object: string
  owned_by: string
  permission: string
  root: string
}

interface IEnabledModel {
  model_name: string
  provider_id: string
}

interface ModelStore {
  models: IModel[]
  modelList: IEnabledModel[]
  loading: boolean
  selectedModel: string
  loadModels: (providerId: string) => Promise<void>
  loadEnabledModels: () => Promise<void>
  loadModelsById : (providerId: string) => Promise<void>
  addNewModel: (providerId: string, modelId: string) => Promise<void>
  setSelectedModel: (modelId: string) => void
  deleteModel: (modelId: number) => Promise<void>
  clearModels: () => void
}

export const useModelStore = create<ModelStore>()(
  devtools(set => ({
    models: [],
    loading: false,
    selectedModel: '',
    modelList: [],

    loadEnabledModels: async () => {
      try {
        set({ loading: true })
        const res = await fetchEnableModels()
        if (res.data.code === 0 && res.data.data.length > 0) {
          set({ modelList: res.data.data })
        } else {
          set({ modelList: [] })
          console.error('模型列表加载失败')
        }
      } catch (error) {
        set({ modelList: [] })
        console.error('加载模型出错', error)
      }
    },

    deleteModel: async  (modelId: number) => {
      await deleteModelById( modelId)
    },
    // 加载模型列表
    loadModels: async (providerId: string) => {
      try {
        set({ loading: true })
        const res = await fetchModels(providerId)
        if (res.data.code === 0 && res.data.data.models.data.length > 0) {
          set({ models: res.data.data.models.data })
        } else if (res.data.code === 0 && res.data.data.models.length > 0) {
          set({ models: res.data.data.models.data })
        } else {
          set({ models: [] })
          console.error('模型列表加载失败')
        }
      } catch (error) {
        set({ models: [] })
        console.error('加载模型出错', error)
      } finally {
        set({ loading: false })
      }
    },
    loadModelsById: async (providerId: string)=>{
      const models  = await fetchEnableModelById(providerId)
      if (models.data.code === 0) {
        console.log('模型列表加载成功:', models.data)
        return models.data.data
      }
  },
    // 新增模型
    addNewModel: async (providerId: string, modelId: string) => {
      try {
        const res = await addModel({ provider_id: providerId, model_name: modelId })
        if (res.code === 0) {
          console.log('新增模型成功:', modelId)
          // ✅ 新增成功以后，前端直接追加一条到 models 列表
          set(state => ({
            models: [
              ...state.models,
              {
                id: modelId,
                created: Date.now(),
                object: 'model',
                owned_by: '',
                permission: '',
                root: '',
              },
            ],
          }))
        } else {
          console.error('新增模型失败')
        }
      } catch (error) {
        console.error('添加模型出错', error)
      }
    },

    // 设置选中的模型
    setSelectedModel: modelId => set({ selectedModel: modelId }),

    // 清空
    clearModels: () => set({ models: [], selectedModel: '' }),
  }))
)
