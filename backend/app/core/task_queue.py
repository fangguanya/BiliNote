import queue
import threading
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import uuid
import os
import json
from app.utils.logger import get_logger
from app.utils.task_utils import save_original_request_data
import traceback

logger = get_logger(__name__)

# --- 单例模式实现 ---
_task_queue_instance = None
_task_queue_lock = threading.Lock()

def get_task_queue(max_workers: int = 3) -> 'TaskQueue':
    """
    获取任务队列的单例。
    """
    global _task_queue_instance
    if _task_queue_instance is None:
        with _task_queue_lock:
            if _task_queue_instance is None:
                logger.error("🚨 [SINGLETON] Creating new TaskQueue instance.")
                _task_queue_instance = TaskQueue(max_workers=max_workers)
            else:
                logger.error("🚨 [SINGLETON] Instance already created while waiting for lock.")
    else:
        logger.error("🚨 [SINGLETON] Returning existing TaskQueue instance.")
    return _task_queue_instance

class TaskType(Enum):
    SINGLE_VIDEO = "single_video"
    COLLECTION = "collection"

class TaskStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

@dataclass
class Task:
    task_id: str
    task_type: TaskType
    data: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = None
    started_at: float = None
    completed_at: float = None
    error_message: str = None
    result: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """将任务对象序列化为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "data": self.data,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "result": self.result
        }

    @classmethod
    def from_dict(cls, data: dict):
        """从字典反序列化为任务对象"""
        status = TaskStatus(data.get('status', 'PENDING'))
        task_type = TaskType(data.get('task_type', 'SINGLE_VIDEO'))
        
        return cls(
            task_id=data['task_id'],
            task_type=task_type,
            data=data['data'],
            status=status,
            created_at=data.get('created_at'),
            started_at=data.get('started_at'),
            completed_at=data.get('completed_at'),
            error_message=data.get('error_message'),
            result=data.get('result')
        )

class TaskQueue:
    def __init__(self, max_workers: int = 3):
        logger.warning(f"✅✅✅ [INSTANCE CHECK] TaskQueue __init__ called. Instance ID: {id(self)}")
        self.task_queue = queue.Queue()
        self.tasks: Dict[str, Task] = {}
        self.max_workers = max_workers
        self.workers = []
        self.running = False
        self._lock = threading.Lock()
        
        # 将持久化目录设置在项目根目录的 'backend' 文件夹下
        # os.path.dirname(__file__) -> backend/app/core
        # os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "task_persistence")) -> backend/task_persistence
        self.persistence_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "task_persistence"))
        os.makedirs(self.persistence_dir, exist_ok=True)
        logger.warning(f"✅ [调试] 任务持久化目录已确认为: {self.persistence_dir}")
        
        self._load_tasks_from_disk()
        
    def _save_task_to_disk(self, task: Task):
        """将单个任务保存到磁盘"""
        file_path = os.path.join(self.persistence_dir, f"{task.task_id}.json")
        logger.error(f"💾 [SAVE_TASK] Attempting to save task to: {file_path}")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(task.to_dict(), f, ensure_ascii=False, indent=4)
            logger.error(f"💾✅ [SAVE_TASK] Successfully saved task: {task.task_id}")
        except Exception as e:
            logger.error(f"❌ 序列化并保存任务失败 {file_path}: {e}")

    def _load_task_from_file(self, task_id: str) -> Optional[Task]:
        """从单个文件加载任务"""
        file_path = os.path.join(self.persistence_dir, f"{task_id}.json")
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            task = Task.from_dict(data)
            return task
        except Exception as e:
            logger.error(f"❌ 从文件反序列化任务失败 {file_path}: {e}")
            return None

    def _load_tasks_from_disk(self):
        """在启动时从磁盘加载所有任务"""
        with self._lock:
            logger.warning(f"📂 [调试] 开始从磁盘加载持久化的任务...")
            if not os.path.exists(self.persistence_dir):
                logger.warning("  - 持久化目录不存在，跳过加载。")
                return

            task_files = [f for f in os.listdir(self.persistence_dir) if f.endswith('.json')]
            if not task_files:
                logger.warning("  - 持久化目录为空，跳过加载。")
                return

            loaded_count = 0
            requeued_count = 0
            for filename in task_files:
                task_id = filename.replace(".json", "")
                try:
                    task = self._load_task_from_file(task_id)
                    if not task:
                        continue

                    # 如果任务在服务关闭时处于正在运行状态，则重置为待处理
                    if task.status == TaskStatus.RUNNING:
                        logger.warning(f"🔄 检测到中断的任务，重置为待处理: {task.task_id}")
                        task.status = TaskStatus.PENDING
                        task.started_at = None
                        self._save_task_to_disk(task)  # 保存重置后的状态

                    self.tasks[task.task_id] = task
                    loaded_count += 1
                    logger.info(f"  - ✅ 已加载任务: {task.task_id} (状态: {task.status.value})")

                    # 只有未完成的任务才需要重新放入队列
                    if task.status not in [TaskStatus.SUCCESS, TaskStatus.FAILED]:
                        logger.info(f"  - 📥 将待处理任务重新放入队列: {task.task_id}")
                        self.task_queue.put(task)
                        requeued_count += 1
                except Exception as e:
                    logger.error(f"❌ 加载任务 {task_id} 失败: {e}", exc_info=True)
            
            logger.info(f"✅ 任务加载完成。共加载 {loaded_count} 个任务，重新入队 {requeued_count} 个。")

    def start(self):
        """启动任务队列处理器"""
        if self.running:
            return
            
        self.running = True
        logger.info(f"🚀 启动任务队列，工作线程数: {self.max_workers}")
        
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker, name=f"TaskWorker-{i}")
            worker.daemon = True
            worker.start()
            self.workers.append(worker)
            
    def stop(self):
        """停止任务队列处理器"""
        self.running = False
        logger.info("🛑 停止任务队列")
        
    def add_task(self, task_type: TaskType, data: Dict[str, Any], task_id: Optional[str] = None) -> str:
        """添加任务到队列"""
        if not task_id:
            task_id = str(uuid.uuid4())
        
        # 保存原始请求数据到持久化存储
        try:
            save_original_request_data(task_id, data)
        except Exception as e:
            logger.warning(f"⚠️ 保存原始请求数据失败: {task_id}, {e}")
            
        task = Task(
            task_id=task_id,
            task_type=task_type,
            data=data,
            created_at=time.time()
        )
        
        with self._lock:
            self.tasks[task_id] = task
            logger.error(f"💾 [ADD_TASK] About to call _save_task_to_disk for {task_id}")
            self._save_task_to_disk(task) # 持久化
            logger.error(f"💾 [ADD_TASK] Returned from _save_task_to_disk for {task_id}")
            
        self.task_queue.put(task)
        logger.warning(f"📝 [INSTANCE CHECK] Task added to queue. Instance ID: {id(self)}. Task ID: {task_id}. Total tasks in memory: {len(self.tasks)}")
        
        return task_id
        
    def get_task_status(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        with self._lock:
            return self.tasks.get(task_id)
            
    def get_all_tasks(self) -> Dict[str, Task]:
        """获取所有任务"""
        with self._lock:
            return self.tasks.copy()
            
    def retry_task(self, task_id: str) -> bool:
        """重试任务（支持重试任何非SUCCESS状态的任务）"""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                logger.warning(f"⚠️ 任务不存在，无法重试: {task_id}")
                return False
            
            if task.status == TaskStatus.SUCCESS:
                logger.warning(f"⚠️ 任务已成功完成，无需重试: {task_id}")
                return False
            
            # 重置任务状态
            task.status = TaskStatus.PENDING
            task.started_at = None
            task.completed_at = None
            task.error_message = None
            task.result = None
            self._save_task_to_disk(task) # 持久化
            
            # 重新提交到队列
            self.task_queue.put(task)
            
        logger.info(f"🔄 任务已重新提交到队列: {task_id}")
        return True
        
    def batch_retry_failed_tasks(self) -> dict:
        """批量重试所有失败的任务"""
        with self._lock:
            failed_tasks = [task for task in self.tasks.values() if task.status == TaskStatus.FAILED]
            
            if not failed_tasks:
                logger.info("📝 没有找到失败的任务")
                return {"retried_count": 0, "total_failed": 0, "message": "没有需要重试的失败任务"}
            
            retried_count = 0
            for task in failed_tasks:
                # 重置任务状态
                task.status = TaskStatus.PENDING
                task.started_at = None
                task.completed_at = None
                task.error_message = None
                task.result = None
                self._save_task_to_disk(task) # 持久化
                
                # 重新提交到队列
                self.task_queue.put(task)
                retried_count += 1
                
        logger.info(f"🔄 批量重试完成，重试了 {retried_count} 个失败任务")
        return {
            "retried_count": retried_count, 
            "total_failed": len(failed_tasks),
            "message": f"成功重试 {retried_count} 个失败任务"
        }
        
    def batch_retry_non_success_tasks(self) -> dict:
        """批量重试所有非成功状态的任务（包括PENDING、RUNNING、FAILED）"""
        with self._lock:
            non_success_tasks = [task for task in self.tasks.values() if task.status != TaskStatus.SUCCESS]
            
            if not non_success_tasks:
                logger.info("📝 没有找到非成功状态的任务")
                return {"retried_count": 0, "total_non_success": 0, "message": "没有需要重试的非成功任务"}
            
            # 按状态分类统计
            pending_count = len([t for t in non_success_tasks if t.status == TaskStatus.PENDING])
            running_count = len([t for t in non_success_tasks if t.status == TaskStatus.RUNNING])
            failed_count = len([t for t in non_success_tasks if t.status == TaskStatus.FAILED])
            
            retried_count = 0
            for task in non_success_tasks:
                # 重置任务状态
                task.status = TaskStatus.PENDING
                task.started_at = None
                task.completed_at = None
                task.error_message = None
                task.result = None
                self._save_task_to_disk(task) # 持久化
                
                # 重新提交到队列
                self.task_queue.put(task)
                retried_count += 1
                
        logger.info(f"🔄 批量重试非成功任务完成，重试了 {retried_count} 个任务")
        logger.info(f"📊 重试统计: PENDING({pending_count}), RUNNING({running_count}), FAILED({failed_count})")
        
        return {
            "retried_count": retried_count, 
            "total_non_success": len(non_success_tasks),
            "pending_count": pending_count,
            "running_count": running_count, 
            "failed_count": failed_count,
            "message": f"成功重试 {retried_count} 个非成功任务 (PENDING:{pending_count}, RUNNING:{running_count}, FAILED:{failed_count})"
        }
        
    def force_retry_all(self, task_ids: List[str], override_data: Optional[dict] = None) -> dict:
        """
        强制重试指定列表中的所有任务。
        不再扫描磁盘，而是基于前端提供的ID列表。
        """
        with self._lock:
            logger.error(f"⚡️ [强制重试] 收到 {len(task_ids)} 个任务的重试请求。")
            logger.error(f"📂 [FORCE_RETRY] Checking persistence directory: {self.persistence_dir}")

            retried_count = 0
            not_found_count = 0
            
            for task_id in task_ids:
                # 首先检查任务队列中是否已存在
                if task_id in self.tasks:
                    task = self.tasks[task_id]
                    
                    # 更新任务数据
                    if override_data:
                        task.data.update(override_data)
                        logger.info(f"  - ⚙️ 应用新配置到任务 {task_id}")

                    # 重置任务状态
                    task.status = TaskStatus.PENDING
                    task.started_at = None
                    task.completed_at = None
                    task.error_message = None
                    task.result = None
                    
                    self.task_queue.put(task)
                    self._save_task_to_disk(task)
                    
                    retried_count += 1
                    logger.info(f"  - ✅ 成功重置并重试任务: {task_id} (内存中)")
                    continue
                
                # 检查task_persistence目录
                task_file = os.path.join(self.persistence_dir, f"{task_id}.json")
                if os.path.exists(task_file):
                    task = self._load_task_from_file(task_id)
                    if task:
                        # 更新任务数据
                        if override_data:
                            task.data.update(override_data)
                            logger.info(f"  - ⚙️ 应用新配置到任务 {task_id}")

                        # 重置任务状态
                        task.status = TaskStatus.PENDING
                        task.started_at = None
                        task.completed_at = None
                        task.error_message = None
                        task.result = None
                        
                        self.tasks[task.task_id] = task
                        self.task_queue.put(task)
                        self._save_task_to_disk(task)
                        
                        retried_count += 1
                        logger.info(f"  - ✅ 成功重置并重试任务: {task_id}")
                        continue
                
                # 检查note_results目录中的任务文件
                note_results_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "note_results"))
                logger.warning(f"  - [DEBUG] 检查note_results绝对路径: {note_results_dir}")
                request_file = os.path.join(note_results_dir, f"{task_id}.request.json")
                
                logger.warning(f"  - [DEBUG] 检查note_results请求文件: {request_file}")
                logger.warning(f"  - [DEBUG] 文件是否存在: {os.path.exists(request_file)}")
                
                if os.path.exists(request_file):
                    try:
                        # 从note_results读取任务数据
                        with open(request_file, 'r', encoding='utf-8') as f:
                            request_data = json.load(f)
                        
                        logger.warning(f"  - [DEBUG] 请求数据的键: {list(request_data.keys())}")
                        
                        # 从请求数据中提取原始请求
                        original_request = request_data.get("original_request", {})
                        
                        logger.warning(f"  - [DEBUG] 原始请求的键: {list(original_request.keys())}")
                        
                        # 检查是否含有必要信息
                        if "video_url" in original_request and "platform" in original_request:
                            # 创建任务
                            task_data = {
                                'video_url': original_request.get('video_url'),
                                'platform': original_request.get('platform'),
                                'quality': original_request.get('quality', 'medium'),
                                'model_name': original_request.get('model_name', 'gpt-4o-mini'),
                                'provider_id': original_request.get('provider_id', 'openai'),
                                'title': original_request.get('title', '未知标题'),
                                'screenshot': original_request.get('screenshot', False),
                                'link': original_request.get('link', False),
                                'format': original_request.get('format', []),
                                'style': original_request.get('style', '简洁'),
                                'extras': original_request.get('extras'),
                                'video_understanding': original_request.get('video_understanding', False),
                                'video_interval': original_request.get('video_interval', 0),
                                'grid_size': original_request.get('grid_size', [])
                            }
                            
                            # 应用覆盖数据
                            if override_data:
                                logger.warning(f"  - [DEBUG] 应用覆盖数据: {override_data}")
                                task_data.update(override_data)
                            
                            logger.warning(f"  - [DEBUG] 最终任务数据: {task_data}")
                            
                            # 创建任务对象
                            task = Task(
                                task_id=task_id,
                                task_type=TaskType.SINGLE_VIDEO,
                                data=task_data,
                                created_at=time.time()
                            )
                            
                            # 保存任务
                            self.tasks[task_id] = task
                            self.task_queue.put(task)
                            self._save_task_to_disk(task)
                            
                            retried_count += 1
                            logger.info(f"  - ✅ 从note_results的request文件成功重建并重试任务: {task_id}")
                            continue
                        else:
                            logger.warning(f"  - [DEBUG] 原始请求缺少必要信息 video_url 或 platform")
                    except Exception as e:
                        logger.error(f"  - ❌ 从note_results加载request文件失败: {task_id}, 错误: {e}")
                        logger.error(f"  - [DEBUG] 异常详情: {traceback.format_exc()}")
                else:
                    logger.warning(f"  - [DEBUG] request文件不存在: {request_file}")
                
                # 尝试使用普通.json文件
                note_file = os.path.join(note_results_dir, f"{task_id}.json")
                if os.path.exists(note_file):
                    try:
                        # 从note_results读取任务数据
                        with open(note_file, 'r', encoding='utf-8') as f:
                            note_data = json.load(f)
                        
                        # 检查是否含有必要信息
                        if "video_url" in note_data and "platform" in note_data:
                            # 创建任务
                            task_data = {
                                'video_url': note_data.get('video_url'),
                                'platform': note_data.get('platform'),
                                'quality': note_data.get('quality', 'medium'),
                                'model_name': note_data.get('model_name', 'gpt-4o-mini'),
                                'provider_id': note_data.get('provider_id', 'openai'),
                                'title': note_data.get('title', '未知标题')
                            }
                            
                            # 应用覆盖数据
                            if override_data:
                                task_data.update(override_data)
                            
                            # 创建任务对象
                            task = Task(
                                task_id=task_id,
                                task_type=TaskType.SINGLE_VIDEO,
                                data=task_data,
                                created_at=time.time()
                            )
                            
                            # 保存任务
                            self.tasks[task_id] = task
                            self.task_queue.put(task)
                            self._save_task_to_disk(task)
                            
                            retried_count += 1
                            logger.info(f"  - ✅ 从note_results成功重建并重试任务: {task_id}")
                            continue
                    except Exception as e:
                        logger.error(f"  - ❌ 从note_results加载任务文件失败: {task_id}, 错误: {e}")
                
                # 如果上述尝试都失败，才计算为未找到
                logger.warning(f"  - ❓ 未找到任务文件，跳过: {task_id}")
                not_found_count += 1

            summary = {
                "retried_count": retried_count,
                "not_found_count": not_found_count,
                "total_requested": len(task_ids),
                "message": f"强制重试完成: {retried_count}个任务成功重试, {not_found_count}个任务未找到。"
            }
            logger.warning(f"  - 📝 [强制重试总结] {summary['message']}")
            return summary
        
    def _worker(self):
        """工作线程主循环"""
        worker_name = threading.current_thread().name
        logger.info(f"🔄 {worker_name} 启动")
        
        while self.running:
            try:
                # 获取任务，设置超时避免阻塞
                task = self.task_queue.get(timeout=1)
                self._process_task(task, worker_name)
                self.task_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"❌ {worker_name} 处理任务时发生错误: {e}")
                
        logger.info(f"🛑 {worker_name} 停止")
        
    def _process_task(self, task: Task, worker_name: str):
        """处理单个任务，增加顶层异常捕获"""
        logger.info(f"🎬 {worker_name} 开始处理任务: {task.task_id}")
        
        try:
            # 更新任务状态为运行中
            with self._lock:
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()
                task.error_message = None
                task.result = None
                self._save_task_to_disk(task) # 持久化
            
            # 执行任务
            if task.task_type == TaskType.SINGLE_VIDEO:
                result = self._process_single_video(task)
            elif task.task_type == TaskType.COLLECTION:
                result = self._process_collection(task)
            else:
                raise ValueError(f"未知的任务类型: {task.task_type}")

            # 更新任务状态为成功
            with self._lock:
                task.status = TaskStatus.SUCCESS
                task.result = result
                self._save_task_to_disk(task) # 持久化
            
            logger.info(f"✅ {worker_name} 任务完成: {task.task_id}")
            
        except Exception as e:
            # 捕获所有可能的异常，确保工作线程不会崩溃
            error_message = f"任务执行失败: {str(e)}"
            logger.error(f"❌ {worker_name} 任务处理失败: {task.task_id}")
            logger.error(f"   错误详情: {traceback.format_exc()}")
            
            # 更新任务状态为失败
            with self._lock:
                task.status = TaskStatus.FAILED
                task.error_message = error_message
                self._save_task_to_disk(task) # 持久化
        
        finally:
            # 确保任务完成时间被记录
            with self._lock:
                task.completed_at = time.time()
                self._save_task_to_disk(task) # 持久化
        
    def _process_single_video(self, task: Task) -> Any:
        """处理单个视频任务"""
        from app.utils.task_process import process_single_video_task
        
        data = task.data
        # 调用task_process中的处理逻辑
        return process_single_video_task(task.task_id, data)
        
    def _process_collection(self, task: Task) -> Any:
        """处理合集任务"""
        from app.utils.task_process import process_collection_task
        
        data = task.data
        # 调用task_process中的处理逻辑
        return process_collection_task(task.task_id, data, self.add_task)

# 全局任务队列实例，【重要】所有模块都应通过 get_task_queue() 获取实例
task_queue = get_task_queue() 