/**
 * BiliNote 存储清理工具
 * 
 * 在浏览器控制台运行此脚本来清理 localStorage
 */

// 方案1：精简所有任务（推荐）
function compactAllTasks() {
  console.log('🗜️ 开始精简任务数据...')
  useTaskStore.getState().compactAllTasks()
  
  const tasks = useTaskStore.getState().tasks
  const sizeKB = (JSON.stringify(tasks).length / 1024).toFixed(2)
  console.log(`✅ 精简完成: ${sizeKB} KB, ${tasks.length} 个任务`)
}

// 方案2：删除失败的任务
function removeFailedTasks() {
  const tasks = useTaskStore.getState().tasks
  const failedTasks = tasks.filter(t => t.status === 'FAILED')
  
  console.log(`❌ 找到 ${failedTasks.length} 个失败任务`)
  
  if (failedTasks.length === 0) {
    console.log('✅ 没有失败的任务需要清理')
    return
  }
  
  if (confirm(`确定要删除 ${failedTasks.length} 个失败任务吗？`)) {
    failedTasks.forEach(t => useTaskStore.getState().removeTask(t.id))
    console.log(`✅ 已删除 ${failedTasks.length} 个失败任务`)
    
    const newSize = (JSON.stringify(useTaskStore.getState().tasks).length / 1024).toFixed(2)
    console.log(`📊 当前大小: ${newSize} KB`)
  }
}

// 方案3：只保留最近N个任务
function keepRecentTasks(count = 50) {
  const tasks = useTaskStore.getState().tasks
  
  if (tasks.length <= count) {
    console.log(`✅ 当前只有 ${tasks.length} 个任务，无需清理`)
    return
  }
  
  // 按创建时间排序
  const sortedTasks = [...tasks].sort((a, b) => 
    new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
  )
  
  const toRemove = sortedTasks.slice(count)
  
  if (confirm(`确定要删除 ${toRemove.length} 个旧任务，只保留最近 ${count} 个吗？`)) {
    toRemove.forEach(t => useTaskStore.getState().removeTask(t.id))
    console.log(`✅ 已删除 ${toRemove.length} 个旧任务`)
    
    const newSize = (JSON.stringify(useTaskStore.getState().tasks).length / 1024).toFixed(2)
    console.log(`📊 当前大小: ${newSize} KB, ${useTaskStore.getState().tasks.length} 个任务`)
  }
}

// 方案4：清空所有任务（慎用！）
function clearAllTasks() {
  const tasks = useTaskStore.getState().tasks
  
  if (confirm(`⚠️ 警告：确定要删除所有 ${tasks.length} 个任务吗？此操作不可恢复！`)) {
    if (confirm('再次确认：真的要删除所有任务吗？')) {
      useTaskStore.getState().clearTasks()
      console.log('✅ 已清空所有任务')
    }
  }
}

// 查看存储使用情况
function checkStorageUsage() {
  const tasks = useTaskStore.getState().tasks
  const taskStorage = localStorage.getItem('task-storage')
  
  console.log('📊 存储使用情况:')
  console.log(`  任务数量: ${tasks.length}`)
  
  if (taskStorage) {
    const sizeKB = (taskStorage.length / 1024).toFixed(2)
    const sizeMB = (taskStorage.length / 1024 / 1024).toFixed(2)
    console.log(`  存储大小: ${sizeKB} KB (${sizeMB} MB)`)
    console.log(`  平均每个任务: ${(taskStorage.length / 1024 / tasks.length).toFixed(2)} KB`)
  }
  
  // 按状态统计
  const statusCount = tasks.reduce((acc, t) => {
    acc[t.status] = (acc[t.status] || 0) + 1
    return acc
  }, {})
  
  console.log('  任务状态分布:')
  Object.entries(statusCount).forEach(([status, count]) => {
    console.log(`    ${status}: ${count}`)
  })
  
  // localStorage 总使用
  let totalSize = 0
  for (let key in localStorage) {
    if (localStorage.hasOwnProperty(key)) {
      totalSize += localStorage[key].length + key.length
    }
  }
  console.log(`  localStorage 总使用: ${(totalSize / 1024).toFixed(2)} KB`)
  console.log(`  localStorage 限制: 约 5-10 MB`)
}

// 导出函数到全局
window.BiliNoteStorage = {
  compactAllTasks,
  removeFailedTasks,
  keepRecentTasks,
  clearAllTasks,
  checkStorageUsage,
}

console.log(`
🛠️ BiliNote 存储清理工具已加载

可用命令：
  BiliNoteStorage.checkStorageUsage()     - 查看存储使用情况
  BiliNoteStorage.compactAllTasks()       - 精简所有任务（推荐）
  BiliNoteStorage.removeFailedTasks()     - 删除失败的任务
  BiliNoteStorage.keepRecentTasks(50)     - 只保留最近50个任务
  BiliNoteStorage.clearAllTasks()         - 清空所有任务（慎用！）

快速使用：
  1. 先查看使用情况: BiliNoteStorage.checkStorageUsage()
  2. 精简任务数据: BiliNoteStorage.compactAllTasks()
  3. 如果还不够，删除失败任务: BiliNoteStorage.removeFailedTasks()
`)

