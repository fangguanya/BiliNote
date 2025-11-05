#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BaiduPCS-Py 统一服务
完全基于BaiduPCS-Py命令行工具，使用正确的参数
支持任务队列，确保下载任务串行执行
"""

import os
import json
import time
import subprocess
import shutil
import re
import threading
import queue
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

from app.utils.logger import get_logger

logger = get_logger(__name__)

class TaskStatus(Enum):
    """任务状态枚举"""
    WAITING = "等待中"
    RUNNING = "运行中"
    COMPLETED = "已完成"
    FAILED = "失败"
    CANCELLED = "已取消"

@dataclass
class DownloadTask:
    """下载任务"""
    task_id: str
    remote_path: str
    local_path: str
    downloader: str = "me"
    concurrency: int = 5
    status: TaskStatus = TaskStatus.WAITING
    progress: float = 0.0
    error_msg: Optional[str] = None
    created_time: float = 0.0
    start_time: Optional[float] = None
    end_time: Optional[float] = None

@dataclass
class BaiduPCSUser:
    """BaiduPCS用户信息"""
    user_name: str
    cookies: str
    bduss: Optional[str] = None
    user_id: Optional[int] = None
    quota_used: Optional[int] = None
    quota_total: Optional[int] = None
    quota_used_readable: Optional[str] = None
    quota_total_readable: Optional[str] = None
    is_default: bool = False
    is_active: bool = False

@dataclass
class BaiduPCSFile:
    """BaiduPCS文件信息"""
    fs_id: str
    filename: str
    path: str
    is_dir: bool
    is_media: bool
    size: int
    size_readable: str
    ctime: int
    mtime: int

class BaiduPCSService:
    """BaiduPCS统一服务类 - 使用正确的命令行参数，支持任务队列"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """实现单例模式，避免多次初始化导致的性能问题"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return
        
        self._check_baidupcs_command()
        # 支持的媒体文件扩展名
        self.video_extensions = {
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', 
            '.webm', '.m4v', '.3gp', '.ts', '.m2ts', '.f4v', 
            '.rmvb', '.rm', '.mpg', '.mpeg', '.vob', '.asf'
            # 注意：.ass 是字幕文件，不是视频文件
        }
        self.audio_extensions = {
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', 
            '.m4a', '.ape', '.ac3', '.dts'
        }
        
        # 任务队列相关
        self._download_queue = queue.Queue()
        self._active_tasks: Dict[str, DownloadTask] = {}
        self._task_results: Dict[str, Dict[str, Any]] = {}
        self._queue_worker_thread = None
        self._queue_lock = threading.Lock()
        self._is_processing = False
        
        # 文件列表缓存（优化性能）
        self._file_list_cache: Dict[str, Tuple[List[Dict], float]] = {}
        self._cache_ttl = 60  # 缓存60秒
        
        # 认证状态缓存（优化性能，避免频繁执行who命令）
        self._auth_cache: Optional[bool] = None
        self._auth_cache_time: float = 0
        self._auth_cache_ttl = 300  # 认证状态缓存5分钟
        
        # 启动任务队列工作线程
        self._start_queue_worker()
        
        # 标记已初始化
        self._initialized = True
        logger.info("✅ BaiduPCSService单例初始化完成")
    
    def _start_queue_worker(self):
        """启动任务队列工作线程"""
        if self._queue_worker_thread is None or not self._queue_worker_thread.is_alive():
            self._queue_worker_thread = threading.Thread(target=self._queue_worker, daemon=True)
            self._queue_worker_thread.start()
            logger.info("🚀 BaiduPCS任务队列工作线程已启动")
    
    def _queue_worker(self):
        """任务队列工作线程 - 确保串行执行"""
        while True:
            try:
                # 从队列中获取任务
                task = self._download_queue.get(timeout=1)
                
                # 检查任务是否已被取消
                if task.status == TaskStatus.CANCELLED:
                    self._download_queue.task_done()
                    continue
                
                # 执行任务
                with self._queue_lock:
                    self._is_processing = True
                    task.status = TaskStatus.RUNNING
                    task.start_time = time.time()
                    logger.info(f"🏃 开始执行下载任务: {task.task_id}")
                
                try:
                    # 实际执行下载
                    result = self._execute_download_task(task)
                    
                    # 更新任务状态
                    with self._queue_lock:
                        if result.get("success", False):
                            task.status = TaskStatus.COMPLETED
                            task.progress = 100.0
                            logger.info(f"✅ 下载任务完成: {task.task_id}")
                        else:
                            task.status = TaskStatus.FAILED
                            task.error_msg = result.get("message", "下载失败")
                            logger.error(f"❌ 下载任务失败: {task.task_id}, 错误: {task.error_msg}")
                        
                        task.end_time = time.time()
                        self._task_results[task.task_id] = result
                        self._is_processing = False
                
                except Exception as e:
                    with self._queue_lock:
                        task.status = TaskStatus.FAILED
                        task.error_msg = str(e)
                        task.end_time = time.time()
                        self._task_results[task.task_id] = {"success": False, "message": str(e)}
                        self._is_processing = False
                        logger.error(f"❌ 下载任务异常: {task.task_id}, 错误: {e}")
                
                finally:
                    self._download_queue.task_done()
                    
            except queue.Empty:
                # 队列空闲，继续循环
                continue
            except Exception as e:
                logger.error(f"❌ 任务队列工作线程异常: {e}")
                with self._queue_lock:
                    self._is_processing = False
    
    def _execute_download_task(self, task: DownloadTask) -> Dict[str, Any]:
        """执行具体的下载任务"""
        try:
            logger.info(f"🔄 开始下载文件: {task.remote_path} -> {task.local_path}")
            
            # 确保输出目录存在
            output_dir = os.path.dirname(task.local_path)
            os.makedirs(output_dir, exist_ok=True)
            
            # 增加逻辑：下载前删除已存在的本地文件
            expected_file = os.path.join(output_dir, os.path.basename(task.remote_path))
            files_to_delete = {task.local_path, expected_file}  # 使用集合避免重复删除
            
            for file_path in files_to_delete:
                if os.path.exists(file_path):
                    try:
                        logger.info(f"🗑️ 发现已存在的本地文件，将在下载前删除: {file_path}")
                        os.remove(file_path)
                        logger.info(f"✅ 已成功删除本地文件: {file_path}")
                    except OSError as e:
                        logger.error(f"❌ 删除本地文件失败: {file_path}, 错误: {e}")
                        return {
                            "success": False,
                            "message": f"删除已存在的本地文件失败: {e}"
                        }
            
            # 构建下载命令
            cmd_args = [
                'download',
                task.remote_path,
                '--outdir', output_dir,
                '--downloader', task.downloader,
                '-s', str(task.concurrency),
                '--chunk-size', '4M'
            ]
            
            logger.info(f"🔧 执行下载命令: BaiduPCS-Py {' '.join(cmd_args)}")
            
            success, stdout, stderr = self._run_baidupcs_command(cmd_args, timeout=1800)  # 30分钟超时
            
            # 🎯 重要：对于下载命令，即使返回码非0，只要文件确实存在且有内容就算成功
            # 检查目标文件是否存在
            actual_file = task.local_path
            
            # 检查可能的文件位置
            download_success = False
            final_file_path = None
            file_size = 0
            download_message = "下载成功"
            
            # 检查是否是文件已存在的情况
            output_text = (stdout + " " + stderr).lower()
            file_already_exists = any(indicator in output_text for indicator in [
                "is ready existed", "already exists", "已存在", "file exists"
            ])
            
            if os.path.exists(actual_file) and os.path.getsize(actual_file) > 0:
                download_success = True
                final_file_path = actual_file
                file_size = os.path.getsize(actual_file)
                if file_already_exists:
                    download_message = "文件已存在，无需重复下载"
            elif os.path.exists(expected_file) and os.path.getsize(expected_file) > 0:
                # 文件下载到了预期位置，需要移动到目标位置
                download_success = True
                final_file_path = actual_file
                if file_already_exists:
                    download_message = "文件已存在，无需重复下载"
                try:
                    shutil.move(expected_file, actual_file)
                    file_size = os.path.getsize(actual_file)
                    logger.info(f"📦 文件已移动到目标位置: {expected_file} -> {actual_file}")
                except Exception as e:
                    logger.warning(f"⚠️ 文件移动失败: {e}, 使用原位置")
                    final_file_path = expected_file
                    file_size = os.path.getsize(expected_file)
            
            if download_success:
                logger.info(f"✅ 文件下载成功: {final_file_path} ({self._format_size(file_size)})")
                if file_already_exists:
                    logger.info(f"💡 {download_message}")
                elif not success:
                    logger.warning(f"⚠️ 命令返回码非0但文件下载成功")
                
                return {
                    "success": True,
                    "message": download_message,
                    "file_path": final_file_path,
                    "file_size": file_size,
                    "remote_path": task.remote_path,
                    "was_existing": file_already_exists
                }
            else:
                # 如果命令执行成功但文件不存在，可能是特殊情况
                if success and file_already_exists:
                    # 命令报告文件已存在，但我们在预期位置找不到文件
                    # 尝试在输出中提取实际文件路径
                    actual_path_match = re.search(r'([^\s]+(?:\.mp4|\.avi|\.mkv|\.mov|\.wmv|\.flv|\.webm|\.m4v|\.mp3|\.wav|\.flac|\.aac))\s+is\s+ready\s+existed', stdout + stderr, re.IGNORECASE)
                    if actual_path_match:
                        existing_file_path = actual_path_match.group(1)
                        if os.path.exists(existing_file_path) and os.path.getsize(existing_file_path) > 0:
                            logger.info(f"✅ 找到已存在的文件: {existing_file_path}")
                            return {
                                "success": True,
                                "message": "文件已存在，无需重复下载",
                                "file_path": existing_file_path,
                                "file_size": os.path.getsize(existing_file_path),
                                "remote_path": task.remote_path,
                                "was_existing": True
                            }
                
                error_msg = stderr or stdout or "下载失败，文件不存在或为空"
                logger.error(f"❌ 下载失败: {error_msg}")
                logger.error(f"   期望文件: {expected_file}")
                logger.error(f"   目标文件: {actual_file}")
                logger.error(f"   命令成功: {success}")
                logger.error(f"   文件已存在标识: {file_already_exists}")
                
                return {
                    "success": False,
                    "message": f"下载失败: {error_msg}",
                    "remote_path": task.remote_path,
                    "local_path": task.local_path
                }
                
        except Exception as e:
            logger.error(f"❌ 执行下载任务异常: {e}")
            return {
                "success": False,
                "message": f"下载异常: {str(e)}"
            }
    
    def add_download_task(self, remote_path: str, local_path: str, 
                         downloader: str = "me", concurrency: int = 5) -> str:
        """添加下载任务到队列"""
        import uuid
        
        task_id = str(uuid.uuid4())
        task = DownloadTask(
            task_id=task_id,
            remote_path=remote_path,
            local_path=local_path,
            downloader=downloader,
            concurrency=concurrency,
            created_time=time.time()
        )
        
        with self._queue_lock:
            self._active_tasks[task_id] = task
        
        self._download_queue.put(task)
        logger.info(f"📝 下载任务已加入队列: {task_id}, 队列长度: {self._download_queue.qsize()}")
        
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        with self._queue_lock:
            task = self._active_tasks.get(task_id)
            if not task:
                return None
            
            return {
                "task_id": task_id,
                "status": task.status.value,
                "progress": task.progress,
                "remote_path": task.remote_path,
                "local_path": task.local_path,
                "error_msg": task.error_msg,
                "created_time": task.created_time,
                "start_time": task.start_time,
                "end_time": task.end_time,
                "duration": (task.end_time - task.start_time) if task.start_time and task.end_time else None
            }
    
    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务结果"""
        return self._task_results.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._queue_lock:
            task = self._active_tasks.get(task_id)
            if not task:
                return False
            
            if task.status == TaskStatus.WAITING:
                task.status = TaskStatus.CANCELLED
                logger.info(f"🚫 任务已取消: {task_id}")
                return True
            else:
                logger.warning(f"⚠️ 无法取消任务（状态: {task.status.value}）: {task_id}")
                return False
    
    def get_queue_info(self) -> Dict[str, Any]:
        """获取队列信息"""
        with self._queue_lock:
            waiting_tasks = [task for task in self._active_tasks.values() if task.status == TaskStatus.WAITING]
            running_tasks = [task for task in self._active_tasks.values() if task.status == TaskStatus.RUNNING]
            completed_tasks = [task for task in self._active_tasks.values() if task.status == TaskStatus.COMPLETED]
            failed_tasks = [task for task in self._active_tasks.values() if task.status == TaskStatus.FAILED]
            
            return {
                "queue_size": self._download_queue.qsize(),
                "is_processing": self._is_processing,
                "total_tasks": len(self._active_tasks),
                "waiting_count": len(waiting_tasks),
                "running_count": len(running_tasks),
                "completed_count": len(completed_tasks),
                "failed_count": len(failed_tasks),
                "active_tasks": [
                    {
                        "task_id": task.task_id,
                        "status": task.status.value,
                        "remote_path": task.remote_path,
                        "progress": task.progress,
                        "created_time": task.created_time
                    }
                    for task in self._active_tasks.values()
                ]
            }
    
    def _check_baidupcs_command(self) -> bool:
        """检查BaiduPCS-Py命令是否可用"""
        try:
            logger.info("🔍 检查BaiduPCS-Py命令行工具...")
            result = subprocess.run(['BaiduPCS-Py', '--version'], 
                                 capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version_info = result.stdout.strip()
                logger.info(f"✅ BaiduPCS-Py命令行工具可用: {version_info}")
                return True
            else:
                logger.error(f"❌ BaiduPCS-Py命令执行失败，返回码: {result.returncode}")
                logger.error(f"错误输出: {result.stderr}")
                return False
        except FileNotFoundError:
            logger.error("❌ BaiduPCS-Py命令未找到，请确保已安装并在PATH中")
            logger.error("💡 安装方法: pip install BaiduPCS-Py")
            return False
        except subprocess.TimeoutExpired:
            logger.error("❌ BaiduPCS-Py命令检查超时")
            return False
        except Exception as e:
            logger.error(f"❌ BaiduPCS-Py命令检查异常: {e}")
            return False
    
    def _run_baidupcs_command(self, cmd_args: List[str], timeout: int = 300) -> Tuple[bool, str, str]:
        """运行BaiduPCS-Py命令"""
        try:
            cmd = ['BaiduPCS-Py'] + cmd_args
            logger.info(f"🔧 执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8'
            )
            
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            success = result.returncode == 0
            
            # 对于某些命令，即使返回码非0也可能是正常的（如who命令）
            # 记录详细信息而不仅仅是成功失败
            logger.debug(f"📋 命令执行完成:")
            logger.debug(f"   返回码: {result.returncode}")
            logger.debug(f"   标准输出长度: {len(stdout)} 字符")
            logger.debug(f"   错误输出长度: {len(stderr)} 字符")
            
            if stdout:
                logger.debug(f"   标准输出前100字符: {stdout[:100]}...")
            if stderr:
                logger.debug(f"   错误输出: {stderr}")
            
            # 对于特定命令，调整成功判断逻辑
            command_name = cmd_args[0] if cmd_args else ""
            
            if command_name == "who":
                # who命令：有用户信息就算成功
                has_user_info = any(keyword in stdout.lower() for keyword in ["user id:", "user name:", "bduss:"])
                if has_user_info:
                    logger.info("✅ who命令执行成功（检测到用户信息）")
                    success = True
                else:
                    logger.warning("⚠️ who命令无用户信息")
            elif command_name == "download":
                # 🎯 下载命令特殊处理：检查是否是文件已存在的情况
                output_text = (stdout + " " + stderr).lower()
                
                # 检查是否包含 "文件已存在" 的标识
                file_exists_indicators = [
                    "is ready existed",
                    "already exists", 
                    "已存在",
                    "file exists"
                ]
                
                has_file_exists = any(indicator in output_text for indicator in file_exists_indicators)
                
                if has_file_exists and not success:
                    logger.info("✅ 下载命令检测到文件已存在，视为成功")
                    success = True
                elif success:
                    logger.info("✅ 下载命令执行成功")
                else:
                    logger.error(f"❌ 下载命令执行失败 (返回码: {result.returncode})")
                    # 输出更详细的错误信息以便调试
                    if stdout:
                        logger.error(f"   标准输出: {stdout}")
                    if stderr:
                        logger.error(f"   错误输出: {stderr}")
            else:
                # 其他命令：按返回码判断
                if success:
                    logger.info("✅ 命令执行成功")
                else:
                    logger.error(f"❌ 命令执行失败 (返回码: {result.returncode})")
            
            return success, stdout, stderr
            
        except subprocess.TimeoutExpired:
            logger.error(f"❌ 命令执行超时 ({timeout}秒)")
            return False, "", "命令执行超时"
        except Exception as e:
            logger.error(f"❌ 运行命令失败: {e}")
            return False, "", str(e)
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def _parse_user_info(self, raw_info: str) -> Dict[str, Any]:
        """解析BaiduPCS-Py的原始用户信息输出"""
        try:
            import re
            
            parsed_info = {}
            
            # 解析用户ID
            user_id_match = re.search(r'user id:\s*(\d+)', raw_info)
            if user_id_match:
                parsed_info['user_id'] = int(user_id_match.group(1))
            
            # 解析用户名
            user_name_match = re.search(r'user name:\s*(.+)', raw_info)
            if user_name_match:
                parsed_info['user_name'] = user_name_match.group(1).strip()
            
            # 解析配额信息 - 格式如: "quota: 6.7 TB/16.1 TB"
            quota_match = re.search(r'quota:\s*([\d.]+)\s*([A-Z]+)\s*/\s*([\d.]+)\s*([A-Z]+)', raw_info)
            if quota_match:
                used_value = float(quota_match.group(1))
                used_unit = quota_match.group(2)
                total_value = float(quota_match.group(3))
                total_unit = quota_match.group(4)
                
                # 转换为字节数
                unit_multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
                
                quota_used_bytes = int(used_value * unit_multipliers.get(used_unit, 1))
                quota_total_bytes = int(total_value * unit_multipliers.get(total_unit, 1))
                
                parsed_info['quota_used'] = quota_used_bytes
                parsed_info['quota_total'] = quota_total_bytes
                parsed_info['quota_used_readable'] = f"{used_value} {used_unit}"
                parsed_info['quota_total_readable'] = f"{total_value} {total_unit}"
                
                # 计算使用百分比
                if quota_total_bytes > 0:
                    usage_percent = (quota_used_bytes / quota_total_bytes) * 100
                    parsed_info['quota_usage_percent'] = round(usage_percent, 1)
                else:
                    parsed_info['quota_usage_percent'] = 0.0
            else:
                # 如果无法解析配额，设置默认值
                parsed_info['quota_used'] = 0
                parsed_info['quota_total'] = 0
                parsed_info['quota_used_readable'] = "0 B"
                parsed_info['quota_total_readable'] = "0 B"
                parsed_info['quota_usage_percent'] = 0.0
            
            logger.debug(f"🔍 解析用户信息结果: {parsed_info}")
            
            return parsed_info
            
        except Exception as e:
            logger.error(f"❌ 解析用户信息失败: {e}")
            return {
                'user_id': 0,
                'user_name': '未知用户',
                'quota_used': 0,
                'quota_total': 0,
                'quota_used_readable': "0 B",
                'quota_total_readable': "0 B",
                'quota_usage_percent': 0.0
            }
    
    def clear_auth_cache(self):
        """清除认证状态缓存（在登录/登出时调用）"""
        self._auth_cache = None
        self._auth_cache_time = 0
        logger.debug("🧹 已清除认证状态缓存")
    
    def clear_file_list_cache(self, path: str = None):
        """
        清除文件列表缓存
        
        Args:
            path: 如果指定，只清除特定路径的缓存；否则清除所有缓存
        """
        if path:
            # 清除特定路径的所有缓存（包括recursive和非recursive）
            keys_to_remove = [k for k in self._file_list_cache.keys() if k.startswith(path)]
            for key in keys_to_remove:
                del self._file_list_cache[key]
            logger.info(f"🗑️ 已清除路径 '{path}' 的文件列表缓存 ({len(keys_to_remove)} 个)")
        else:
            # 清除所有缓存
            count = len(self._file_list_cache)
            self._file_list_cache.clear()
            logger.info(f"🗑️ 已清除所有文件列表缓存 ({count} 个)")
    
    def is_authenticated(self, force_check: bool = False) -> bool:
        """
        检查是否已认证
        
        Args:
            force_check: 是否强制检查（忽略缓存）
        """
        try:
            # 检查缓存
            if not force_check and self._auth_cache is not None:
                cache_age = time.time() - self._auth_cache_time
                if cache_age < self._auth_cache_ttl:
                    logger.debug(f"🎯 使用认证状态缓存 (缓存{int(cache_age)}秒前): {self._auth_cache}")
                    return self._auth_cache
            
            # 执行实际检查，使用较短的超时时间
            logger.debug("🔍 执行认证状态检查...")
            success, stdout, stderr = self._run_baidupcs_command(['who'], timeout=10)
            
            # BaiduPCS-Py的who命令在没有默认用户时返回码可能是1，但仍有用户信息
            # 所以我们主要检查输出内容而不是返回码
            has_user_info = (
                "user id:" in stdout.lower() or 
                "用户" in stdout or
                "user name:" in stdout.lower() or
                "bduss:" in stdout.lower()
            )
            
            logger.debug(f"🔍 认证检查 - 返回码: {success}, 有用户信息: {has_user_info}")
            
            # 更新缓存
            self._auth_cache = has_user_info
            self._auth_cache_time = time.time()
            
            if has_user_info:
                logger.info("✅ 用户已认证")
                return True
            else:
                logger.warning("⚠️ 用户未认证或无有效用户信息")
                if stderr:
                    logger.debug(f"错误输出: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 认证检查失败: {e}")
            # 出错时不更新缓存，返回False
            return False
    
    def add_user_by_cookies(self, cookies: str) -> Dict[str, Any]:
        """通过cookies添加用户"""
        try:
            # 移除不存在的--no-check参数，使用正确的命令
            success, stdout, stderr = self._run_baidupcs_command([
                'useradd', 
                '--cookies', cookies
            ], timeout=30)  # 30秒超时
            
            if success:
                logger.info(f"✅ 用户添加成功")
                # 清除认证缓存，强制重新检查
                self.clear_auth_cache()
                return {"success": True, "message": "用户添加成功"}
            else:
                error_msg = stderr or stdout or "未知错误"
                logger.error(f"❌ 添加用户失败: {error_msg}")
                
                # 检查是否是因为用户已存在
                if "already exist" in error_msg.lower() or "已存在" in error_msg:
                    logger.info("⚠️ 用户可能已存在，尝试检查当前用户")
                    # 清除缓存后重新检查
                    self.clear_auth_cache()
                    if self.is_authenticated():
                        return {"success": True, "message": "用户已存在且已认证"}
                
                return {"success": False, "message": f"添加用户失败: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ 添加用户异常: {e}")
            return {"success": False, "message": f"添加用户失败: {str(e)}"}
    
    def add_user_by_bduss(self, bduss: str, stoken: str = None) -> Dict[str, Any]:
        """通过BDUSS添加用户"""
        try:
            args = ['useradd', '--bduss', bduss]
            if stoken:
                # 注意：检查BaiduPCS-Py是否支持stoken参数
                args.extend(['--stoken', stoken])
            
            success, stdout, stderr = self._run_baidupcs_command(args, timeout=30)
            
            if success:
                logger.info(f"✅ 用户添加成功")
                # 清除认证缓存，强制重新检查
                self.clear_auth_cache()
                return {"success": True, "message": "用户添加成功"}
            else:
                error_msg = stderr or stdout or "未知错误"
                logger.error(f"❌ 添加用户失败: {error_msg}")
                
                # 检查是否是因为用户已存在
                if "already exist" in error_msg.lower() or "已存在" in error_msg:
                    logger.info("⚠️ 用户可能已存在，尝试检查当前用户")
                    # 清除缓存后重新检查
                    self.clear_auth_cache()
                    if self.is_authenticated():
                        return {"success": True, "message": "用户已存在且已认证"}
                
                return {"success": False, "message": f"添加用户失败: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ 添加用户异常: {e}")
            return {"success": False, "message": f"添加用户失败: {str(e)}"}
    
    def get_user_info(self) -> Dict[str, Any]:
        """获取用户信息"""
        try:
            success, stdout, stderr = self._run_baidupcs_command(['who'], timeout=10)
            
            if success:
                return {"success": True, "info": stdout}
            else:
                return {"success": False, "message": "获取用户信息失败"}
                
        except Exception as e:
            return {"success": False, "message": f"获取用户信息失败: {str(e)}"}
    
    def download_file(self, remote_path: str, local_path: str, 
                     downloader: str = "me", concurrency: int = 5, 
                     wait_for_completion: bool = True, timeout: int = 1800) -> Dict[str, Any]:
        """下载文件 - 使用任务队列确保串行执行"""
        try:
            # 增强认证检查，包含更详细的错误信息
            if not self.is_authenticated():
                logger.error(f"❌ 用户未认证，无法下载文件: {remote_path}")
                return {"success": False, "message": "用户未认证，请检查BaiduPCS-Py登录状态"}
            
            # 验证文件路径
            if not remote_path or not remote_path.strip():
                return {"success": False, "message": "远程路径不能为空"}
            
            # 记录下载开始
            logger.info(f"📥 开始下载文件: {remote_path} -> {local_path}")
            logger.info(f"🔧 下载配置: downloader={downloader}, concurrency={concurrency}")
            
            # 添加任务到队列
            task_id = self.add_download_task(remote_path, local_path, downloader, concurrency)
            
            if not wait_for_completion:
                # 异步模式：立即返回任务ID
                return {
                    "success": True,
                    "message": "任务已添加到队列",
                    "task_id": task_id,
                    "async": True
                }
            
            # 同步模式：等待任务完成
            logger.info(f"⏳ 等待下载任务完成: {task_id}")
            start_time = time.time()
            last_status_check = 0
            
            while True:
                current_time = time.time()
                
                # 检查超时
                if current_time - start_time > timeout:
                    self.cancel_task(task_id)
                    logger.error(f"❌ 下载超时 ({timeout}秒): {remote_path}")
                    return {
                        "success": False,
                        "message": f"下载超时 ({timeout}秒)",
                        "task_id": task_id,
                        "remote_path": remote_path
                    }
                
                # 每5秒记录一次状态，避免日志过多
                if current_time - last_status_check > 5:
                    logger.debug(f"⏱️ 下载进行中，已等待 {int(current_time - start_time)} 秒")
                    last_status_check = current_time
                
                # 检查任务状态
                status = self.get_task_status(task_id)
                if not status:
                    logger.error(f"❌ 下载任务不存在: {task_id}")
                    return {
                        "success": False,
                        "message": "任务不存在，可能已被清理",
                        "task_id": task_id,
                        "remote_path": remote_path
                    }
                
                if status["status"] == TaskStatus.COMPLETED.value:
                    result = self.get_task_result(task_id)
                    if result:
                        result["task_id"] = task_id
                        logger.info(f"✅ 下载任务成功完成: {task_id}")
                        return result
                    else:
                        logger.warning(f"⚠️ 下载任务完成但无结果: {task_id}")
                        return {
                            "success": True,
                            "message": "任务完成",
                            "task_id": task_id,
                            "remote_path": remote_path
                        }
                elif status["status"] == TaskStatus.FAILED.value:
                    error_msg = status.get("error_msg", "任务失败")
                    logger.error(f"❌ 下载任务失败: {task_id}, 错误: {error_msg}")
                    
                    # 检查是否是认证问题
                    if "认证" in error_msg or "unauthorized" in error_msg.lower():
                        logger.error("🔐 检测到认证问题，建议重新登录BaiduPCS-Py")
                    
                    return {
                        "success": False,
                        "message": f"下载失败: {error_msg}",
                        "task_id": task_id,
                        "remote_path": remote_path,
                        "error_type": "task_failed"
                    }
                elif status["status"] == TaskStatus.CANCELLED.value:
                    logger.warning(f"⚠️ 下载任务已取消: {task_id}")
                    return {
                        "success": False,
                        "message": "任务已取消",
                        "task_id": task_id,
                        "remote_path": remote_path
                    }
                
                # 等待一段时间后再检查
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"❌ 下载文件异常: {e}")
            logger.error(f"   远程路径: {remote_path}")
            logger.error(f"   本地路径: {local_path}")
            return {
                "success": False,
                "message": f"下载异常: {str(e)}",
                "remote_path": remote_path,
                "local_path": local_path,
                "error_type": "exception"
            }
    
    def get_file_list(self, path: str = "/", use_cache: bool = True, recursive: bool = False) -> Dict[str, Any]:
        """
        获取文件列表 - 使用正确的 BaiduPCS-Py 命令参数
        
        Args:
            path: 目录路径
            use_cache: 是否使用缓存（默认True，可提高性能）
            recursive: 是否递归获取子目录（默认False）
        """
        try:
            if not self.is_authenticated():
                return {"success": False, "message": "用户未认证"}
            
            # 强制不使用缓存（临时修复：确保获取最新数据）
            #logger.info(f"⚡ 强制清除缓存以获取最新文件列表")
            #self.clear_file_list_cache(path)
            
            # 检查缓存 - 缓存key需要包含recursive参数
            cache_key = f"{path}|recursive={recursive}"
            if use_cache and cache_key in self._file_list_cache:
                cached_files, cache_time = self._file_list_cache[cache_key]
                if time.time() - cache_time < self._cache_ttl:
                    logger.info(f"🎯 使用缓存的文件列表: {path} (recursive={recursive}, 缓存{int(time.time() - cache_time)}秒前)")
                    return {"success": True, "files": cached_files}
            
            # 构建命令参数
            cmd_args = ['ls']
            if recursive:
                cmd_args.append('-R')  # 递归列出子目录
            cmd_args.append(path)
            
            # 根据 BaiduPCS-Py 官方文档，ls 命令的正确用法是：
            # BaiduPCS-Py ls [OPTIONS] [REMOTEPATHS]...
            # 使用较短的超时时间以提高响应速度
            logger.info(f"🔍 获取文件列表: {path} (recursive={recursive})")
            logger.info(f"📋 执行命令: BaiduPCS-Py {' '.join(cmd_args)}")
            success, stdout, stderr = self._run_baidupcs_command(cmd_args, timeout=15)  # 缩短到15秒
            
            # 对于 ls 命令，即使返回码非0，只要有输出内容就可能是成功的
            # BaiduPCS-Py在某些情况下即使成功也会返回非0状态码
            if not success:
                if stdout.strip():
                    # 有输出内容，可能是成功的，只是返回码异常
                    logger.debug(f"⚠️ ls命令返回码非0但有输出内容，继续解析")
                else:
                    # 没有输出内容，确实失败了
                    error_msg = stderr or "获取文件列表失败"
                    logger.error(f"❌ 获取文件列表失败: {error_msg}")
                    return {"success": False, "message": f"获取文件列表失败: {error_msg}"}
            
            if not stdout.strip():
                logger.info("📁 目录为空")
                return {"success": True, "files": []}
            
            # 关键修复：BaiduPCS-Py在显示长路径时会插入换行符！
            # 需要先清理这些换行符，然后再按行解析
            # 策略：将所有连续的 \n + 空格 替换为空字符串
            import re
            
            # 先记录原始输出
            logger.info(f"🔍 原始输出长度: {len(stdout)} 字符")
            logger.debug(f"🔍 原始输出前500字符:\n{repr(stdout[:500])}")
            
            # 清理换行符的策略：
            # 1. 首先保护真正的行分隔符（目录标记行、文件行、表格线）
            # 2. 将剩余的所有 \n 都删除（这些是显示换行，不是逻辑换行）
            
            # 标记真正的行分隔符：在它们前面添加特殊标记
            cleaned_stdout = re.sub(r'\n(d )', r'<<LINE_BREAK>>\1', stdout)  # 目录行
            cleaned_stdout = re.sub(r'\n(- )', r'<<LINE_BREAK>>\1', cleaned_stdout)  # 文件行
            cleaned_stdout = re.sub(r'\n(───)', r'<<LINE_BREAK>>\1', cleaned_stdout)  # 表格线
            cleaned_stdout = re.sub(r'\n(  Path)', r'<<LINE_BREAK>>\1', cleaned_stdout)  # 表头
            cleaned_stdout = re.sub(r'\n(/)', r'<<LINE_BREAK>>\1', cleaned_stdout)  # 目录路径行（以/开头）
            
            # 删除所有剩余的 \n（这些都是显示换行）
            cleaned_stdout = cleaned_stdout.replace('\n', '')
            
            # 恢复真正的行分隔符
            cleaned_stdout = cleaned_stdout.replace('<<LINE_BREAK>>', '\n')
            
            logger.info(f"🧹 清理后输出长度: {len(cleaned_stdout)} 字符")
            logger.debug(f"🔍 清理后输出前500字符:\n{repr(cleaned_stdout[:500])}")
            
            # 解析 BaiduPCS-Py ls 命令的实际输出格式
            files = []
            lines = cleaned_stdout.split('\n')
            logger.info(f"🔍 解析文件列表输出，共 {len(lines)} 行")
            if stderr:
                logger.info(f"⚠️ 错误输出:\n{stderr}")
            
            # 递归模式下，需要追踪当前目录
            current_dir = path
            
            for i, line in enumerate(lines):
                original_line = line
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                
                # 在递归模式下，目录路径会单独显示（如：/path/to/dir 或 /path/to/dir:）
                # 改进：更严格的目录路径识别
                if recursive:
                    # 检查是否是目录路径标记行
                    # 格式：/完整/路径 或 /完整/路径:
                    # 必须以 / 开头，不能是文件/目录行前缀
                    if (line_stripped.startswith('/') and 
                        not line_stripped.startswith('d ') and 
                        not line_stripped.startswith('- ')):
                        # 这是一个新的目录路径
                        # 移除末尾的冒号（如果有）
                        current_dir = line_stripped.rstrip(':')
                        logger.info(f"📁 递归模式 - 切换到目录: {current_dir}")
                        continue
                
                # 使用原始行的strip版本进行后续处理
                line = line_stripped
                
                # 跳过表头、路径显示和分隔符
                # 改进：添加更多跳过条件，避免误判
                skip_patterns = [
                    line.startswith('─'),
                    line.startswith('='),
                    line == 'Path',
                    line.startswith('  Path'),
                    line == path,  # 跳过路径显示行
                    line.startswith('总计'),
                    line.startswith('共'),
                    'items' in line.lower(),
                    line.startswith('Size'),  # 跳过 Size 列标题
                    line.startswith('Modified'),  # 跳过 Modified 列标题
                    line.startswith('Path:'),  # 跳过 Path: 显示
                    line.endswith('个文件') or line.endswith('folders'),  # 跳过统计行
                ]
                
                if any(skip_patterns):
                    logger.debug(f"⏭️ 跳过表头/统计行 [{i}]: {line}")
                    continue
                
                try:
                    # BaiduPCS-Py ls 的实际输出格式：
                    # d 目录名
                    # - 文件名
                    
                    is_dir = False
                    filename = ""
                    
                    if line.startswith('d '):
                        # 目录
                        is_dir = True
                        filename = line[2:].strip()
                        # 递归模式下，文件名可能包含相对路径，只取最后的文件名
                        if recursive and '/' in filename:
                            original_filename = filename
                            filename = os.path.basename(filename)
                            logger.info(f"🔧 [{i}] 提取纯目录名: '{original_filename}' -> '{filename}'")
                        logger.debug(f"🔵 识别为目录 [{i}]: '{filename}'")
                    elif line.startswith('- '):
                        # 文件
                        is_dir = False
                        filename = line[2:].strip()
                        # 递归模式下，文件名可能包含相对路径，只取最后的文件名
                        if recursive and '/' in filename:
                            original_filename = filename
                            filename = os.path.basename(filename)
                            logger.info(f"🔧 [{i}] 提取纯文件名: '{original_filename}' -> '{filename}'")
                        logger.debug(f"📄 识别为文件 [{i}]: '{filename}'")
                    else:
                        # 其他格式，可能是没有前缀的文件名或者是需要跳过的行
                        # 改进：更谨慎地处理，记录日志但不一定解析
                        logger.warning(f"⚠️ 未知格式 [{i}]: '{line}' (原始: '{original_line}')")
                        # 跳过不识别的行，避免误判
                        continue
                    
                    # 如果文件名为空，跳过
                    if not filename:
                        logger.debug(f"⏭️ 跳过空文件名行 [{i}]: {original_line}")
                        continue
                    
                    # 验证文件名是否合理（不应该是路径）
                    if filename.count('/') > 0:
                        logger.warning(f"⚠️ 文件名包含路径分隔符，可能解析错误 [{i}]: '{filename}'")
                        # 继续处理，但记录警告
                    
                    # 生成 fs_id (使用文件名的哈希)
                    fs_id = f"file_{abs(hash(filename)) % 1000000}"
                    
                    # 构建文件路径（递归模式下使用current_dir，非递归模式使用path）
                    # 改进：使用 os.path.join 确保路径正确
                    base_path = current_dir if recursive else path
                    file_path = os.path.join(base_path, filename).replace('\\', '/')
                    
                    logger.info(f"📁 [{i}] 构建路径: base='{base_path}', name='{filename}', path='{file_path}', recursive={recursive}")
                    
                    # 判断是否为媒体文件
                    is_media = not is_dir and self._is_media_file(filename)
                    
                    # 生成时间戳（当前时间）
                    current_time = int(time.time())
                    
                    file_info = {
                        'fs_id': str(fs_id),
                        'filename': filename,
                        'path': file_path,
                        'is_dir': is_dir,
                        'is_media': is_media,
                        'size': 0,  # BaiduPCS-Py 基础 ls 命令不返回大小信息
                        'size_readable': "未知大小",
                        'ctime': current_time,
                        'mtime': current_time
                    }
                    
                    files.append(file_info)
                    logger.info(f"✅ 解析文件 [{i}]: '{filename}' -> '{file_path}' (dir: {is_dir}, media: {is_media}, base_path: {base_path})")
                
                except Exception as parse_error:
                    logger.warning(f"⚠️ 解析文件行失败 {i}: '{original_line}', 错误: {parse_error}")
                    continue
            
            logger.info(f"✅ 解析文件列表成功，共 {len(files)} 个项目")
            
            # 缓存结果 - 使用包含recursive的缓存key
            if use_cache:
                self._file_list_cache[cache_key] = (files, time.time())
                logger.debug(f"💾 已缓存文件列表: {path} (recursive={recursive})")
            
            return {"success": True, "files": files}
                
        except Exception as e:
            logger.error(f"❌ 获取文件列表异常: {e}")
            return {"success": False, "message": f"获取文件列表失败: {str(e)}"}
    
    def _is_media_file(self, filename: str) -> bool:
        """判断是否为媒体文件"""
        logger.info(f"🔍 检查媒体文件: '{filename}'")
        
        # 提取扩展名
        file_ext = os.path.splitext(filename)[1].lower()
        logger.info(f"   📌 扩展名: '{file_ext}'")
        
        # 检查是否为视频或音频
        is_video = file_ext in self.video_extensions
        is_audio = file_ext in self.audio_extensions
        is_media = is_video or is_audio
        
        logger.info(f"   {'✅' if is_media else '❌'} 是视频: {is_video}, 是音频: {is_audio}, 结果: {is_media}")
        
        if not is_media:
            logger.info(f"   ℹ️ 支持的视频扩展名: {sorted(self.video_extensions)}")
        
        return is_media
    
    def upload_file(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        """上传文件"""
        try:
            if not self.is_authenticated():
                return {"success": False, "message": "用户未认证"}
            
            if not os.path.exists(local_path):
                return {"success": False, "message": f"本地文件不存在: {local_path}"}
            
            remote_dir = os.path.dirname(remote_path)
            
            success, stdout, stderr = self._run_baidupcs_command(['upload', local_path, remote_dir], timeout=7200)
            
            if success:
                return {"success": True, "message": "上传成功"}
            else:
                return {"success": False, "message": f"上传失败: {stderr or stdout}"}
                
        except Exception as e:
            return {"success": False, "message": f"上传失败: {str(e)}"}

# 创建全局实例
baidupcs_service = BaiduPCSService()