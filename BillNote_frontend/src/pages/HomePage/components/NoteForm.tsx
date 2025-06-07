/* NoteForm.tsx ---------------------------------------------------- */
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form.tsx'
import { useEffect, useState } from 'react'
import { useForm, useWatch, FieldErrors } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import { Info, Loader2, Plus, CheckCircle, XCircle, Clock } from 'lucide-react'
import { message, Alert } from 'antd'
import { generateNote, AuthError } from '@/services/note.ts'
import LoginModal from '@/components/LoginModal'
import { uploadFile } from '@/services/upload.ts'
import { useTaskStore } from '@/store/taskStore'
import { useModelStore } from '@/store/modelStore'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip.tsx'
import { Checkbox } from '@/components/ui/checkbox.tsx'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import { Button } from '@/components/ui/button.tsx'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select.tsx'
import { Input } from '@/components/ui/input.tsx'
import { Textarea } from '@/components/ui/textarea.tsx'
import { noteStyles, noteFormats, videoPlatforms } from '@/constant/note.ts'

/* -------------------- 校验 Schema -------------------- */
const formSchema = z.object({
  platform: z.string().min(1, '请选择平台'),
  video_url: z.string().min(1, '请输入视频链接'),
  model_name: z.string().min(1, '请选择模型'),
  style: z.string().min(1, '请选择笔记风格'),
  quality: z.string().min(1, '请选择质量'),
  format: z.array(z.string()).optional().default([]),
  screenshot: z.boolean().optional().default(false),
  link: z.boolean().optional().default(false),
  extras: z.string().optional(),
  video_understanding: z.boolean().optional().default(false),
  video_interval: z.number().min(1).max(60).optional().default(4),
  grid_size: z.array(z.number()).optional().default([3, 3]),
  max_collection_videos: z.number().min(1).max(400).optional().default(200),
  auto_save_notion: z.boolean().optional().default(false),
})

type NoteFormValues = z.infer<typeof formSchema>

/* -------------------- 可复用子组件 -------------------- */
const SectionHeader = ({ title, tip }: { title: string; tip?: string }) => (
  <div className="my-3 flex items-center justify-between">
    <h2 className="block">{title}</h2>
    {tip && (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Info className="hover:text-primary h-4 w-4 cursor-pointer text-neutral-400" />
          </TooltipTrigger>
          <TooltipContent className="text-xs">{tip}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )}
  </div>
)

const CheckboxGroup = ({
  value = [],
  onChange,
  disabledMap,
}: {
  value?: string[]
  onChange: (v: string[]) => void
  disabledMap: Record<string, boolean>
}) => (
  <div className="flex flex-wrap space-x-1.5">
    {noteFormats.map(({ label, value: v }) => (
      <label key={v} className="flex items-center space-x-2">
        <Checkbox
          checked={value.includes(v)}
          disabled={disabledMap[v]}
          onCheckedChange={checked =>
            onChange(checked ? [...value, v] : value.filter(x => x !== v))
          }
        />
        <span>{label}</span>
      </label>
    ))}
  </div>
)

/* -------------------- 主组件 -------------------- */
const NoteForm = () => {
  /* ---- 全局状态 ---- */
  const { addPendingTask, addPendingTasks, currentTaskId, setCurrentTask, getCurrentTask, retryTask } =
    useTaskStore()
  const { loadEnabledModels, modelList } = useModelStore()

  /* ---- State 状态管理 ---- */
  const [uploading, setUploading] = useState(false)
  const [submitting, setSubmitting] = useState(false)  // 新增：提交状态
  
  /* ---- 登录弹窗状态 ---- */
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [loginPlatform, setLoginPlatform] = useState('')
  const [pendingFormData, setPendingFormData] = useState<NoteFormValues | null>(null)

  /* ---- 表单 ---- */
  const form = useForm<NoteFormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      platform: 'bilibili',
      quality: 'medium',
      model_name: modelList[0]?.model_name || '',
      style: 'minimal',
      video_interval: 4,
      grid_size: [3, 3],
      format: [],
      max_collection_videos: 200,
      auto_save_notion: false,
      screenshot: false,
      link: false,
      video_understanding: false,
    },
  })
  const currentTask = getCurrentTask()

  /* ---- 派生状态 ---- */
  const platform = useWatch({ control: form.control, name: 'platform' }) as string
  const editing = currentTask && currentTask.id

  /* ---- 副作用 ---- */
  useEffect(() => {
    loadEnabledModels()
  }, [])

  useEffect(() => {
    if (!currentTask) return
    const { formData } = currentTask

    form.reset({
      platform: formData.platform || 'bilibili',
      video_url: formData.video_url || '',
      model_name: formData.model_name || modelList[0]?.model_name || '',
      style: formData.style || 'minimal',
      quality: formData.quality || 'medium',
      extras: formData.extras || '',
      screenshot: formData.screenshot ?? false,
      link: formData.link ?? false,
      video_understanding: formData.video_understanding ?? false,
      video_interval: formData.video_interval ?? 4,
      grid_size: formData.grid_size ?? [3, 3],
      format: formData.format ?? [],
      max_collection_videos: formData.max_collection_videos ?? 200,
      auto_save_notion: formData.auto_save_notion ?? false,
    })
  }, [currentTaskId, modelList.length, currentTask?.formData])

  /* ---- 帮助函数 ---- */
  const isGenerating = () => !['SUCCESS', 'FAILED', undefined].includes(getCurrentTask()?.status)
  const generating = isGenerating()
  
  const handleFileUpload = async (file: File, cb: (url: string) => void) => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      setUploading(true)
      const { data } = await uploadFile(formData)
      if (data.code === 0) cb(data.data.url)
    } catch (err) {
      console.error('上传失败:', err)
      message.error('上传失败，请重试')
    } finally {
      setUploading(false)
    }
  }

  const onSubmit = async (values: NoteFormValues) => {
    // 如果是重试任务，不需要设置submitting状态
    if (currentTaskId) {
      retryTask(currentTaskId, {
        ...values,
        provider_id: modelList.find(m => m.model_name === values.model_name)!.provider_id,
        task_id: currentTaskId,
      })
      return
    }

    // 新任务提交，设置submitting状态
    setSubmitting(true)
    
    try {
      const payload: any = {
        ...values,
        provider_id: modelList.find(m => m.model_name === values.model_name)!.provider_id,
        task_id: '',
      }

      console.log('📤 提交数据:', payload)
      const response = await generateNote(payload)
      console.log('📥 收到响应:', response)
      
      if (!response) {
        console.error('❌ 收到空响应')
        message.error('任务提交失败')
        return
      }
      
      // 检查是否为合集响应
      if (response.isCollection && response.taskList) {
        // 批量添加任务
        console.log('🎬 处理合集，添加任务:', response.taskList)
        addPendingTasks(response.taskList, values.platform, payload)
        message.success(`已成功为合集中的 ${response.taskList.length} 个视频创建任务！`)
        // 重置编辑状态
        setCurrentTask(null)
      } else if (!response.isCollection && response.data?.task_id) {
        // 单个视频任务
        console.log('📺 处理单视频，添加任务:', response.data.task_id)
        addPendingTask(response.data.task_id, values.platform, payload)
        message.success('任务已提交！')
        // 重置编辑状态
        setCurrentTask(null)
      } else {
        console.error('❌ 响应格式错误:', response)
        message.error('响应格式错误')
      }
    } catch (error: any) {
      console.error('提交任务失败:', error)
      
      // 检查是否为认证错误
      if (error.type === 'AUTH_REQUIRED' && error.authError) {
        const authError = error.authError as AuthError
        console.log('🔐 需要登录认证:', authError.platform)
        
        // 保存当前表单数据，登录成功后重新提交
        setPendingFormData(values)
        setLoginPlatform(authError.platform)
        setShowLoginModal(true)
        
        message.warning(`需要${authError.platform === 'bilibili' ? 'B站' : '抖音'}登录认证`)
        return
      }
      
      message.error('任务提交失败，请重试')
    } finally {
      // 无论成功失败，都要重置提交状态
      setSubmitting(false)
    }
  }
  
  const onInvalid = (errors: FieldErrors<NoteFormValues>) => {
    console.warn('表单校验失败：', errors)
    message.error('请完善所有必填项后再提交')
  }
  
  const handleCreateNew = () => {
    setCurrentTask(null)
  }
  
  const FormButton = () => {
    // 按钮状态只控制提交过程，不受任务生成状态影响
    const isSubmitDisabled = submitting || uploading
    
    let label = '生成笔记'
    let showLoading = false
    
    if (submitting) {
      label = '提交中...'
      showLoading = true
    } else if (uploading) {
      label = '上传中...'
      showLoading = true
    } else if (editing) {
      label = '重新生成'
    }

    return (
      <div className="flex gap-2">
        <Button
          type="submit"
          className={!editing ? 'w-full' : 'w-2/3' + ' bg-primary'}
          disabled={isSubmitDisabled}
        >
          {showLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {label}
        </Button>

        {editing && (
          <Button type="button" variant="outline" className="w-1/3" onClick={handleCreateNew}>
            <Plus className="mr-2 h-4 w-4" />
            新建笔记
          </Button>
        )}
      </div>
    )
  }

  /* ---- 登录处理函数 ---- */
  const handleLoginSuccess = async () => {
    console.log('✅ 登录成功，重新提交任务')
    
    if (pendingFormData) {
      // 登录成功后重新提交表单
      await onSubmit(pendingFormData)
      setPendingFormData(null)
    }
  }

  const handleLoginClose = () => {
    setShowLoginModal(false)
    setLoginPlatform('')
    setPendingFormData(null)
  }

  /* ---- 渲染部分 ---- */
  return (
    <div className="space-y-6">
      {/* 任务状态显示区域 */}
      {currentTask && (
        <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {generating ? (
                <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
              ) : currentTask.status === 'FAILED' ? (
                <XCircle className="h-4 w-4 text-red-500" />
              ) : (
                <Clock className="h-4 w-4 text-gray-500" />
              )}
              <div>
                <p className="text-sm font-medium">
                  {generating ? '正在生成笔记...' : 
                   currentTask.status === 'SUCCESS' ? '笔记生成完成' :
                   currentTask.status === 'FAILED' ? '生成失败' : '任务排队中'}
                </p>
                <p className="text-xs text-neutral-500">
                  任务ID: {currentTask.id}
                </p>
              </div>
            </div>
            {currentTask.status === 'FAILED' && (
              <Button size="sm" variant="outline" onClick={() => form.handleSubmit(onSubmit)()}>
                重试
              </Button>
            )}
          </div>
        </div>
      )}

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit, onInvalid)} className="space-y-4">
          {/* 平台选择 */}
          <FormField
            control={form.control}
            name="platform"
            render={({ field }) => (
              <FormItem>
                <FormLabel>视频平台</FormLabel>
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="选择视频平台" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {videoPlatforms.map(platform => (
                      <SelectItem key={platform.value} value={platform.value}>
                        <div className="flex items-center gap-2">
                          <div className="h-4 w-4">
                            <platform.logo />
                          </div>
                          {platform.label}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* 视频链接 */}
          <FormField
            control={form.control}
            name="video_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>视频链接</FormLabel>
                <FormControl>
                  {platform === 'local' ? (
                    <div className="space-y-2">
                      <Input
                        placeholder="点击上传本地视频文件"
                        value={field.value}
                        readOnly
                      />
                      <input
                        type="file"
                        accept="video/*"
                        onChange={e => {
                          const file = e.target.files?.[0]
                          if (file) handleFileUpload(file, field.onChange)
                        }}
                        className="w-full rounded border border-neutral-300 px-3 py-2 text-sm"
                      />
                    </div>
                  ) : (
                    <Input
                      placeholder={`请输入${
                        videoPlatforms.find(p => p.value === platform)?.label || '视频'
                      }链接（支持单个视频或合集链接）`}
                      {...field}
                    />
                  )}
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* 合集设置 */}
          {platform !== 'local' && (
            <FormField
              control={form.control}
              name="max_collection_videos"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="flex items-center gap-2">
                    合集处理
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger>
                          <Info className="h-4 w-4 text-neutral-500" />
                        </TooltipTrigger>
                        <TooltipContent>
                          <p>如果输入的是合集链接，将自动处理合集中的所有视频</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </FormLabel>
                  <FormControl>
                    <div className="space-y-2">
                      <Input
                        type="number"
                        min="1"
                        max="400"
                        placeholder="最大处理视频数量"
                        value={field.value || 200}
                        onChange={e => field.onChange(parseInt(e.target.value) || 200)}
                      />
                      <p className="text-xs text-neutral-500">
                        设置从合集中最多处理多少个视频（1-400个）
                      </p>
                    </div>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          <div className="grid grid-cols-2 gap-2">
            {/* 模型选择 */}
            <FormField
              control={form.control}
              name="model_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>AI 模型</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="选择模型" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {modelList.map(model => (
                        <SelectItem key={model.model_name} value={model.model_name}>
                          {model.model_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* 笔记风格 */}
            <FormField
              control={form.control}
              name="style"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>笔记风格</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="选择笔记风格" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {noteStyles.map(style => (
                        <SelectItem key={style.value} value={style.value}>
                          {style.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          {/* 格式选择 */}
          <FormField
            control={form.control}
            name="format"
            render={({ field }) => (
              <FormItem>
                <FormLabel>笔记格式</FormLabel>
                <FormControl>
                  <CheckboxGroup
                    value={field.value || []}
                    onChange={field.onChange}
                    disabledMap={{
                      screenshot: platform === 'local',
                      link: platform === 'local',
                    }}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* 质量设置 */}
          <FormField
            control={form.control}
            name="quality"
            render={({ field }) => (
              <FormItem>
                <FormLabel>音频质量</FormLabel>
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="选择音频质量" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="fast">快速 (32kbps)</SelectItem>
                    <SelectItem value="medium">中等 (64kbps)</SelectItem>
                    <SelectItem value="slow">高质 (128kbps)</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* 额外要求 */}
          <FormField
            control={form.control}
            name="extras"
            render={({ field }) => (
              <FormItem>
                <FormLabel>额外要求 (可选)</FormLabel>
                <FormControl>
                  <Textarea
                    placeholder="描述你对笔记内容的特殊要求..."
                    className="resize-none"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Notion自动保存选项 */}
          <FormField
            control={form.control}
            name="auto_save_notion"
            render={({ field }) => (
              <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md border p-4">
                <FormControl>
                  <Checkbox
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
                <div className="space-y-1 leading-none">
                  <FormLabel className="flex items-center gap-2 cursor-pointer">
                    自动保存到 Notion
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger>
                          <Info className="h-4 w-4 text-neutral-500" />
                        </TooltipTrigger>
                        <TooltipContent>
                          <p>生成笔记完成后自动保存到您的 Notion 工作区</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </FormLabel>
                  <p className="text-sm text-neutral-500">
                    需要先在生成的笔记页面配置 Notion 连接
                  </p>
                </div>
              </FormItem>
            )}
          />

          <FormButton />
        </form>
      </Form>

      {/* 登录弹窗 */}
      <LoginModal
        isOpen={showLoginModal}
        onClose={handleLoginClose}
        platform={loginPlatform}
        onLoginSuccess={handleLoginSuccess}
      />
    </div>
  )
}

export default NoteForm
