'use client'

import { useEffect, useState } from 'react'
import { Copy, Download, BrainCircuit, ExternalLink, CheckCircle, Zap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import NotionExport from '@/components/NotionExport'
import { useTaskStore } from '@/store/taskStore'

interface VersionNote {
  ver_id: string
  model_name?: string
  style?: string
  created_at?: string
}

interface NoteHeaderProps {
  currentTask?: {
    markdown: VersionNote[] | string
    audioMeta?: {
      title?: string
    }
    notion?: {
      saved: boolean
      pageId?: string
      pageUrl?: string
      savedAt?: string
      autoSave?: boolean
    }
  }
  isMultiVersion: boolean
  currentVerId: string
  setCurrentVerId: (id: string) => void
  modelName: string
  style: string
  noteStyles: { value: string; label: string }[]
  onCopy: () => void
  onDownload: () => void
  createAt?: string | Date
  setShowTranscribe: (show: boolean) => void
  showTranscribe: boolean
  viewMode: 'map' | 'preview'
  setViewMode: (mode: 'map' | 'preview') => void
}

export function MarkdownHeader({
  currentTask,
  isMultiVersion,
  currentVerId,
  setCurrentVerId,
  modelName,
  style,
  noteStyles,
  onCopy,
  onDownload,
  createAt,
  showTranscribe,
  setShowTranscribe,
  viewMode,
  setViewMode,
}: NoteHeaderProps) {
  const [copied, setCopied] = useState(false)
  const [isRetrying, setIsRetrying] = useState(false)
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const retryTask = useTaskStore(state => state.retryTask)

  useEffect(() => {
    let timer: NodeJS.Timeout
    if (copied) {
      timer = setTimeout(() => setCopied(false), 2000)
    }
    return () => clearTimeout(timer)
  }, [copied])

  const handleCopy = () => {
    onCopy()
    setCopied(true)
  }

  const handleForceRetry = async () => {
    if (!currentTaskId) return
    
    setIsRetrying(true)
    try {
      // 使用强制重试API，即使是成功状态的任务也能重试
      const { force_retry_task } = await import('@/services/note')
      await force_retry_task(currentTaskId)
      
      // 更新前端状态为PENDING
      const updateTaskContent = useTaskStore.getState().updateTaskContent
      updateTaskContent(currentTaskId, { status: 'PENDING' })
      
    } catch (error) {
      console.error('强制重试失败:', error)
    } finally {
      setIsRetrying(false)
    }
  }

  const styleName = noteStyles.find(v => v.value === style)?.label || style

  const reversedMarkdown: VersionNote[] = Array.isArray(currentTask?.markdown)
    ? [...currentTask!.markdown].reverse()
    : []

  const formatDate = (date: string | Date | undefined) => {
    if (!date) return ''
    const d = typeof date === 'string' ? new Date(date) : date
    if (isNaN(d.getTime())) return ''
    return d
      .toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
      .replace(/\//g, '-')
  }

  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b bg-white/95 px-4 py-2 backdrop-blur-sm">
      {/* 左侧区域：版本 + 标签 + 创建时间 */}
      <div className="flex flex-wrap items-center gap-3">
        {isMultiVersion && (
          <Select value={currentVerId} onValueChange={setCurrentVerId}>
            <SelectTrigger className="h-8 w-[160px] text-sm">
              <div className="flex items-center">
                {(() => {
                  const markdown = currentTask?.markdown
                  if (Array.isArray(markdown)) {
                    const idx = markdown.findIndex((v: VersionNote) => v.ver_id === currentVerId)
                    return idx !== -1 ? `版本（${currentVerId.slice(-6)}）` : ''
                  }
                  return ''
                })()}
              </div>
            </SelectTrigger>

            <SelectContent>
              {Array.isArray(currentTask?.markdown) ? 
                currentTask.markdown.map((v: VersionNote, idx: number) => {
                  const shortId = v.ver_id.slice(-6)
                  return (
                    <SelectItem key={v.ver_id} value={v.ver_id}>
                      {`版本（${shortId}）`}
                    </SelectItem>
                  )
                }) : []
              }
            </SelectContent>
          </Select>
        )}

        <Badge variant="secondary" className="bg-pink-100 text-pink-700 hover:bg-pink-200">
          {modelName}
        </Badge>
        <Badge variant="secondary" className="bg-cyan-100 text-cyan-700 hover:bg-cyan-200">
          {styleName}
        </Badge>

        {createAt && (
          <div className="text-muted-foreground text-sm">创建时间: {formatDate(createAt)}</div>
        )}

        {/* Notion保存状态 */}
        {currentTask?.notion?.saved && (
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 hover:bg-green-100">
              <CheckCircle className="w-3 h-3 mr-1" />
              已保存到Notion
            </Badge>
            {currentTask.notion.pageUrl && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={() => window.open(currentTask.notion!.pageUrl, '_blank')}
                    >
                      <ExternalLink className="w-3 h-3" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>打开Notion页面</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
        )}
      </div>

      {/* 右侧操作按钮 */}
      <div className="flex items-center gap-1">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                onClick={() => {
                  setViewMode(viewMode == 'preview' ? 'map' : 'preview')
                }}
                variant="ghost"
                size="sm"
                className="h-8 px-2"
              >
                <BrainCircuit className="mr-1.5 h-4 w-4" />
                <span className="text-sm">{viewMode == 'preview' ? '思维导图' : 'markdown'}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>思维导图</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button onClick={handleCopy} variant="ghost" size="sm" className="h-8 px-2">
                <Copy className="mr-1.5 h-4 w-4" />
                <span className="text-sm">{copied ? '已复制' : '复制'}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>复制内容</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {/* 强制重试按钮 */}
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button 
                onClick={handleForceRetry} 
                variant="ghost" 
                size="sm" 
                className="h-8 px-2"
                disabled={isRetrying || !currentTaskId}
              >
                <Zap className={`mr-1.5 h-4 w-4 ${isRetrying ? 'animate-pulse' : ''}`} />
                <span className="text-sm">{isRetrying ? '重试中...' : '强制重试'}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>强制重新生成此笔记</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button onClick={onDownload} variant="ghost" size="sm" className="h-8 px-2">
                <Download className="mr-1.5 h-4 w-4" />
                <span className="text-sm">导出 Markdown</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>下载为 Markdown 文件</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                onClick={() => {
                  setShowTranscribe(!showTranscribe)
                }}
                variant="ghost"
                size="sm"
                className="h-8 px-2"
              >
                {/*<Download className="mr-1.5 h-4 w-4" />*/}
                <span className="text-sm">原文参照</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>原文参照</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {/* Notion导出按钮 */}
        {currentTaskId && (
          <NotionExport
            taskId={currentTaskId}
            noteTitle={currentTask?.audioMeta?.title || '未命名笔记'}
            disabled={false}
          />
        )}
      </div>
    </div>
  )
}
