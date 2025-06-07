import queue
import threading
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import uuid
from app.utils.logger import get_logger

logger = get_logger(__name__)

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

class TaskQueue:
    def __init__(self, max_workers: int = 3):
        self.task_queue = queue.Queue()
        self.tasks: Dict[str, Task] = {}
        self.max_workers = max_workers
        self.workers = []
        self.running = False
        self._lock = threading.Lock()
        
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
        
    def add_task(self, task_type: TaskType, data: Dict[str, Any], task_id: str = None) -> str:
        """添加任务到队列"""
        if not task_id:
            task_id = str(uuid.uuid4())
            
        task = Task(
            task_id=task_id,
            task_type=task_type,
            data=data,
            created_at=time.time()
        )
        
        with self._lock:
            self.tasks[task_id] = task
            
        self.task_queue.put(task)
        logger.info(f"📝 任务已添加到队列: {task_id} ({task_type.value})")
        
        return task_id
        
    def get_task_status(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        with self._lock:
            return self.tasks.get(task_id)
            
    def get_all_tasks(self) -> Dict[str, Task]:
        """获取所有任务"""
        with self._lock:
            return self.tasks.copy()
            
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
        """处理单个任务"""
        logger.info(f"🎬 {worker_name} 开始处理任务: {task.task_id}")
        
        # 更新任务状态为运行中
        with self._lock:
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            
        try:
            if task.task_type == TaskType.SINGLE_VIDEO:
                result = self._process_single_video(task)
            elif task.task_type == TaskType.COLLECTION:
                result = self._process_collection(task)
            else:
                raise ValueError(f"未知任务类型: {task.task_type}")
                
            # 任务成功完成
            with self._lock:
                task.status = TaskStatus.SUCCESS
                task.completed_at = time.time()
                task.result = result
                
            logger.info(f"✅ {worker_name} 任务完成: {task.task_id}")
            
        except Exception as e:
            # 任务失败
            with self._lock:
                task.status = TaskStatus.FAILED
                task.completed_at = time.time()
                task.error_message = str(e)
                
            logger.error(f"❌ {worker_name} 任务失败: {task.task_id}, 错误: {e}")
            
    def _process_single_video(self, task: Task) -> Any:
        """处理单个视频任务"""
        from app.routers.note import run_note_task
        
        data = task.data
        logger.info(f"📺 处理单视频: {data.get('video_url')}")
        
        # 调用原有的视频处理逻辑
        result = run_note_task(
            task_id=task.task_id,
            video_url=data['video_url'],
            platform=data['platform'],
            quality=data['quality'],
            link=data.get('link', False),
            screenshot=data.get('screenshot', False),
            model_name=data['model_name'],
            provider_id=data['provider_id'],
            _format=data.get('format', []),
            style=data.get('style'),
            extras=data.get('extras'),
            video_understanding=data.get('video_understanding', False),
            video_interval=data.get('video_interval', 0),
            grid_size=data.get('grid_size', [])
        )
        
        return result
        
    def _process_collection(self, task: Task) -> Any:
        """处理合集任务"""
        from app.utils.url_parser import extract_collection_videos
        
        data = task.data
        logger.info(f"🎬 处理合集: {data.get('video_url')}")
        
        # 提取合集视频列表
        videos = extract_collection_videos(
            data['video_url'],
            data['platform'],
            data.get('max_collection_videos', 50)
        )
        
        logger.info(f"📹 合集包含 {len(videos)} 个视频")
        
        # 为每个视频创建单独的任务
        created_tasks = []
        for video_url, title in videos:
            video_task_data = data.copy()
            video_task_data['video_url'] = video_url
            video_task_data['title'] = title
            
            video_task_id = self.add_task(TaskType.SINGLE_VIDEO, video_task_data)
            created_tasks.append({
                'task_id': video_task_id,
                'video_url': video_url,
                'title': title
            })
            
        logger.info(f"✅ 合集处理完成，创建了 {len(created_tasks)} 个子任务")
        
        return {
            'total_videos': len(videos),
            'created_tasks': len(created_tasks),
            'task_list': created_tasks
        }

# 全局任务队列实例
task_queue = TaskQueue(max_workers=3) 