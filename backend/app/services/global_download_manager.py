#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
全局下载管理器
确保整个应用中同时只能下载一个百度网盘文件，避免并发冲突
"""

import threading
import time
import queue
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import uuid

from app.utils.logger import get_logger

logger = get_logger(__name__)

class DownloadStatus(Enum):
    """下载状态"""
    WAITING = "等待中"
    DOWNLOADING = "下载中"
    COMPLETED = "已完成"
    FAILED = "失败"
    CANCELLED = "已取消"

@dataclass
class GlobalDownloadTask:
    """全局下载任务"""
    task_id: str
    platform: str  # "baidu_pan", "bilibili", etc.
    url: str
    local_path: str
    download_func: Callable  # 实际的下载函数
    download_args: tuple = ()
    download_kwargs: dict = None
    status: DownloadStatus = DownloadStatus.WAITING
    progress: float = 0.0
    error_msg: Optional[str] = None
    created_time: float = 0.0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    result: Optional[Any] = None

class GlobalDownloadManager:
    """全局下载管理器 - 确保同时只有一个下载任务"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self._download_queue = queue.Queue()
        self._active_tasks: Dict[str, GlobalDownloadTask] = {}
        self._task_results: Dict[str, Any] = {}
        self._current_task: Optional[GlobalDownloadTask] = None
        self._worker_thread = None
        self._queue_lock = threading.Lock()
        self._is_running = False
        
        # 启动工作线程
        self._start_worker()
        logger.info("🌍 全局下载管理器已初始化")
    
    def _start_worker(self):
        """启动工作线程"""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._is_running = True
            self._worker_thread = threading.Thread(target=self._worker, daemon=True)
            self._worker_thread.start()
            logger.info("🚀 全局下载工作线程已启动")
    
    def _worker(self):
        """工作线程 - 串行处理下载任务"""
        while self._is_running:
            try:
                # 从队列获取任务
                task = self._download_queue.get(timeout=1)
                
                # 检查任务是否已被取消
                if task.status == DownloadStatus.CANCELLED:
                    self._download_queue.task_done()
                    continue
                
                # 执行下载任务
                with self._queue_lock:
                    self._current_task = task
                    task.status = DownloadStatus.DOWNLOADING
                    task.start_time = time.time()
                
                logger.info(f"🌍 全局下载管理器开始下载: {task.platform} - {task.url}")
                
                try:
                    # 调用实际的下载函数
                    if task.download_kwargs is None:
                        task.download_kwargs = {}
                    
                    logger.info(f"🔧 全局下载管理器调用下载函数: {task.download_func.__name__}")
                    logger.info(f"   参数: args={task.download_args}, kwargs={task.download_kwargs}")
                    
                    result = task.download_func(*task.download_args, **task.download_kwargs)
                    
                    logger.info(f"🔍 全局下载管理器收到下载函数返回结果:")
                    logger.info(f"   结果类型: {type(result)}")
                    logger.info(f"   结果是否有success属性: {hasattr(result, 'success')}")
                    logger.info(f"   结果是否是字典: {isinstance(result, dict)}")
                    
                    if hasattr(result, '__dict__'):
                        logger.info(f"   结果对象属性: {list(result.__dict__.keys())}")
                    
                    if isinstance(result, dict):
                        logger.info(f"   字典键值: {list(result.keys())}")
                        logger.info(f"   success键值: {result.get('success', 'N/A')}")
                    
                    # 更新任务状态
                    with self._queue_lock:
                        task.status = DownloadStatus.COMPLETED
                        task.progress = 100.0
                        task.result = result
                        task.end_time = time.time()
                        self._task_results[task.task_id] = result
                        self._current_task = None
                    
                    logger.info(f"✅ 全局下载完成: {task.task_id}")
                    logger.info(f"🔍 已存储结果到task_results，类型: {type(result)}")
                
                except Exception as e:
                    logger.error(f"❌ 全局下载管理器调用下载函数异常: {e}")
                    logger.error(f"   异常类型: {type(e)}")
                    with self._queue_lock:
                        task.status = DownloadStatus.FAILED
                        task.error_msg = str(e)
                        task.end_time = time.time()
                        self._task_results[task.task_id] = {"success": False, "error": str(e)}
                        self._current_task = None
                    
                    logger.error(f"❌ 全局下载失败: {task.task_id}, 错误: {e}")
                
                finally:
                    self._download_queue.task_done()
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"❌ 全局下载工作线程异常: {e}")
                with self._queue_lock:
                    if self._current_task:
                        self._current_task.status = DownloadStatus.FAILED
                        self._current_task.error_msg = str(e)
                        self._current_task = None
    
    def add_download_task(self, platform: str, url: str, local_path: str, 
                         download_func: Callable, *args, **kwargs) -> str:
        """添加下载任务"""
        task_id = str(uuid.uuid4())
        
        task = GlobalDownloadTask(
            task_id=task_id,
            platform=platform,
            url=url,
            local_path=local_path,
            download_func=download_func,
            download_args=args,
            download_kwargs=kwargs,
            created_time=time.time()
        )
        
        with self._queue_lock:
            self._active_tasks[task_id] = task
        
        self._download_queue.put(task)
        
        queue_size = self._download_queue.qsize()
        logger.info(f"📝 全局下载任务已加入队列: {platform} - {task_id[:8]}... (队列长度: {queue_size})")
        
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        with self._queue_lock:
            task = self._active_tasks.get(task_id)
            if not task:
                return None
            
            return {
                "task_id": task_id,
                "platform": task.platform,
                "status": task.status.value,
                "progress": task.progress,
                "url": task.url,
                "local_path": task.local_path,
                "error_msg": task.error_msg,
                "created_time": task.created_time,
                "start_time": task.start_time,
                "end_time": task.end_time,
                "duration": (task.end_time - task.start_time) if task.start_time and task.end_time else None
            }
    
    def get_task_result(self, task_id: str) -> Optional[Any]:
        """获取任务结果"""
        return self._task_results.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._queue_lock:
            task = self._active_tasks.get(task_id)
            if not task:
                return False
            
            if task.status == DownloadStatus.WAITING:
                task.status = DownloadStatus.CANCELLED
                logger.info(f"🚫 全局下载任务已取消: {task_id}")
                return True
            else:
                logger.warning(f"⚠️ 无法取消任务（状态: {task.status.value}）: {task_id}")
                return False
    
    def get_global_status(self) -> Dict[str, Any]:
        """获取全局下载状态"""
        with self._queue_lock:
            current_task_info = None
            if self._current_task:
                current_task_info = {
                    "task_id": self._current_task.task_id,
                    "platform": self._current_task.platform,
                    "url": self._current_task.url,
                    "progress": self._current_task.progress,
                    "start_time": self._current_task.start_time
                }
            
            waiting_tasks = [task for task in self._active_tasks.values() if task.status == DownloadStatus.WAITING]
            downloading_tasks = [task for task in self._active_tasks.values() if task.status == DownloadStatus.DOWNLOADING]
            completed_tasks = [task for task in self._active_tasks.values() if task.status == DownloadStatus.COMPLETED]
            failed_tasks = [task for task in self._active_tasks.values() if task.status == DownloadStatus.FAILED]
            
            return {
                "is_downloading": self._current_task is not None,
                "current_task": current_task_info,
                "queue_size": self._download_queue.qsize(),
                "total_tasks": len(self._active_tasks),
                "waiting_count": len(waiting_tasks),
                "downloading_count": len(downloading_tasks),
                "completed_count": len(completed_tasks),
                "failed_count": len(failed_tasks),
                "recent_tasks": [
                    {
                        "task_id": task.task_id,
                        "platform": task.platform,
                        "status": task.status.value,
                        "url": task.url[:50] + "..." if len(task.url) > 50 else task.url,
                        "created_time": task.created_time
                    }
                    for task in sorted(self._active_tasks.values(), key=lambda t: t.created_time, reverse=True)[:10]
                ]
            }
    
    def is_downloading(self) -> bool:
        """检查是否有任务正在下载"""
        with self._queue_lock:
            return self._current_task is not None
    
    def wait_for_completion(self, task_id: str, timeout: int = 1800) -> Dict[str, Any]:
        """等待任务完成"""
        start_time = time.time()
        
        while True:
            # 检查超时
            if time.time() - start_time > timeout:
                self.cancel_task(task_id)
                logger.error(f"❌ 全局下载管理器任务超时: {task_id}")
                return {
                    "success": False,
                    "message": f"下载超时 ({timeout}秒)",
                    "task_id": task_id
                }
            
            # 检查任务状态
            status = self.get_task_status(task_id)
            if not status:
                logger.error(f"❌ 全局下载管理器任务不存在: {task_id}")
                return {
                    "success": False,
                    "message": "任务不存在",
                    "task_id": task_id
                }
            
            if status["status"] == DownloadStatus.COMPLETED.value:
                result = self.get_task_result(task_id)
                logger.info(f"🔍 全局下载管理器任务完成，开始判断结果: {task_id}")
                logger.info(f"🔍 结果对象类型: {type(result)}")
                logger.info(f"🔍 结果内容: {result}")
                
                if result:
                    # 检查result是否有success属性
                    has_success_attr = hasattr(result, 'success')
                    logger.info(f"🔍 结果是否有success属性: {has_success_attr}")
                    
                    if has_success_attr:
                        success_value = result.success
                        logger.info(f"🔍 success属性值: {success_value}")
                        if success_value:
                            logger.info(f"✅ 全局下载管理器判断为成功（通过success属性）: {task_id}")
                            return {
                                "success": True,
                                "result": result,
                                "task_id": task_id
                            }
                    
                    # 检查result是否是字典且包含success键
                    is_dict = isinstance(result, dict)
                    logger.info(f"🔍 结果是否是字典: {is_dict}")
                    
                    if is_dict:
                        dict_success_value = result.get("success", False)
                        logger.info(f"🔍 字典success键值: {dict_success_value}")
                        if dict_success_value:
                            logger.info(f"✅ 全局下载管理器判断为成功（通过字典success键）: {task_id}")
                            return {
                                "success": True,
                                "result": result,
                                "task_id": task_id
                            }
                    
                    # 🎯 新增：检查是否是AudioDownloadResult类型
                    is_audio_result = hasattr(result, 'file_path') and hasattr(result, 'title') and hasattr(result, 'platform')
                    logger.info(f"🔍 结果是否是AudioDownloadResult类型: {is_audio_result}")
                    
                    if is_audio_result:
                        logger.info(f"✅ 全局下载管理器判断为成功（AudioDownloadResult类型）: {task_id}")
                        logger.info(f"   文件路径: {getattr(result, 'file_path', 'N/A')}")
                        logger.info(f"   标题: {getattr(result, 'title', 'N/A')}")
                        logger.info(f"   平台: {getattr(result, 'platform', 'N/A')}")
                        return {
                            "success": True,
                            "result": result,
                            "task_id": task_id
                        }
                    
                    # 如果都不满足，记录详细信息后返回失败
                    logger.error(f"❌ 全局下载管理器结果判断失败: {task_id}")
                    logger.error(f"   - 有success属性: {has_success_attr}")
                    if has_success_attr:
                        logger.error(f"   - success属性值: {getattr(result, 'success', 'N/A')}")
                    logger.error(f"   - 是字典: {is_dict}")
                    if is_dict:
                        logger.error(f"   - success键值: {result.get('success', 'N/A')}")
                        logger.error(f"   - 所有键: {list(result.keys())}")
                    logger.error(f"   - 是AudioDownloadResult: {is_audio_result}")
                    
                    return {
                        "success": False,
                        "message": "下载失败",
                        "result": result,
                        "task_id": task_id
                    }
                else:
                    logger.warning(f"⚠️ 全局下载管理器任务完成但无结果: {task_id}")
                    return {
                        "success": True,
                        "message": "任务完成",
                        "task_id": task_id
                    }
            elif status["status"] == DownloadStatus.FAILED.value:
                error_msg = status.get("error_msg", "任务失败")
                logger.error(f"❌ 全局下载管理器任务失败: {task_id}, 错误: {error_msg}")
                return {
                    "success": False,
                    "message": error_msg,
                    "task_id": task_id
                }
            elif status["status"] == DownloadStatus.CANCELLED.value:
                logger.warning(f"⚠️ 全局下载管理器任务已取消: {task_id}")
                return {
                    "success": False,
                    "message": "任务已取消",
                    "task_id": task_id
                }
            
            # 等待一段时间后再检查
            time.sleep(1)

# 创建全局单例
global_download_manager = GlobalDownloadManager() 