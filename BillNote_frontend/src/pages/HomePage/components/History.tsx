import NoteHistory from '@/pages/HomePage/components/NoteHistory.tsx'
import { useTaskStore } from '@/store/taskStore'
import { Info, Clock, Loader2 } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import BatchNotionSync from '@/components/BatchNotionSync'
import ForceBatchNotionSync from '@/components/ForceBatchNotionSync'
import BatchRetry from '@/components/BatchRetry'
import ForceRetryAll from '@/components/ForceRetryAll'

const History = () => {
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const isLoading = useTaskStore(state => state.isLoading)
  const isInitialized = useTaskStore(state => state.isInitialized)
  
  return (
    <>
      <div className={'flex h-full w-full flex-col gap-4 px-2.5 py-1.5'}>
        {/*生成历史    */}
        <div className="my-4 flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-neutral-500" />
            <h2 className="text-base font-medium text-neutral-900">生成历史</h2>
          </div>
          {/* 批量操作按钮 - 修改为垂直排布 */}
          <div className="flex flex-col items-end gap-1">
            <BatchRetry />
            <ForceRetryAll />
            <BatchNotionSync />
            <ForceBatchNotionSync />
          </div>
        </div>
        <ScrollArea className="w-full sm:h-[480px] md:h-[720px] lg:h-[92%]">
          {!isInitialized || isLoading ? (
            <div className="flex items-center justify-center h-32 text-gray-500">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              <span>
                {!isInitialized ? '正在初始化任务数据...' : '正在加载任务...'}
              </span>
            </div>
          ) : (
            <NoteHistory onSelect={setCurrentTask} selectedId={currentTaskId} />
          )}
        </ScrollArea>
      </div>
    </>
  )
}

export default History
