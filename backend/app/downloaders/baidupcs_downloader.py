#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
基于BaiduPCS-Py的百度网盘下载器
完全使用BaiduPCS-Py的用户管理和文件操作功能
"""

import os
import tempfile
import subprocess
import json
from typing import Optional, List, Dict, Tuple, Union
from pathlib import Path


from app.downloaders.base import Downloader, DownloadQuality, QUALITY_MAP
from app.models.notes_model import AudioDownloadResult
from app.services.baidupcs_service import BaiduPCSService, BaiduPCSFile
from app.exceptions.auth_exceptions import AuthRequiredException
from app.utils.logger import get_logger
from app.utils.title_cleaner import smart_title_clean

logger = get_logger(__name__)


class BaiduPCSDownloader(Downloader):
    """
    基于BaiduPCS-Py的百度网盘下载器
    """
    
    def __init__(self):
        super().__init__()
        
        # 使用新的BaiduPCS服务
        self.pcs_service = BaiduPCSService()
        
        # 支持的视频和音频格式
        self.video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.m2ts', '.f4v', '.rmvb', '.rm'}
        self.audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.ape', '.ac3', '.dts'}
        
        logger.info("🔧 BaiduPCS下载器初始化完成")
    
    def add_user(self, cookies: str, bduss: str = None) -> bool:
        """
        添加百度网盘用户
        
        Args:
            cookies: 完整的cookies字符串
            bduss: BDUSS值（可选）
            
        Returns:
            bool: 是否添加成功
        """
        result = self.pcs_service.add_user(cookies=cookies, bduss=bduss)
        return result.get("success", False)
    
    def remove_user(self, user_id: int = None) -> bool:
        """移除用户"""
        result = self.pcs_service.remove_user(user_id=user_id)
        return result.get("success", False)
    
    def get_users(self) -> List[Dict[str, any]]:
        """获取用户列表"""
        return self.pcs_service.get_users()
    
    def get_current_user_info(self) -> Optional[Dict[str, any]]:
        """获取当前用户信息"""
        return self.pcs_service.get_current_user_info()
    
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return self.pcs_service.is_authenticated()
    
    def get_file_list(self, path: str = "/", share_code: str = None, extract_code: str = None) -> List[Dict[str, any]]:
        """
        获取文件列表
        
        Args:
            path: 目录路径
            share_code: 分享码（暂不支持）
            extract_code: 提取码（暂不支持）
            
        Returns:
            List[Dict]: 文件列表
        """
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        # 注意：BaiduPCS-Py主要用于个人文件，分享链接功能可能有限
        if share_code:
            logger.warning("⚠️ 当前版本暂不支持分享链接解析")
            return []
        
        result = self.pcs_service.get_file_list(path)
        if not result.get("success", False):
            return []
        files = result.get("files", [])
        
        # 文件列表已经是正确的格式，直接返回
        return files
    
    def search_files(self, keyword: str, path: str = "/") -> List[Dict[str, any]]:
        """搜索文件"""
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        # TODO: 实现搜索功能
        logger.warning("⚠️ 搜索功能暂未实现")
        return []
    
    def get_media_files(self, path: str = "/") -> List[Dict[str, any]]:
        """获取媒体文件"""
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        # TODO: 实现媒体文件过滤功能
        logger.warning("⚠️ 媒体文件过滤功能暂未实现")
        return []
    
    def can_download(self, url: str) -> bool:
        """检查是否可以下载该URL"""
        # 支持百度网盘路径和fs_id
        if url.startswith("baidu_pan://"):
            return True
        
        # 支持网盘路径
        if url.startswith("/") and self.is_authenticated():
            return True
        
        return False
    
    def download_audio(self, url: str, download_path: str, 
                      quality: DownloadQuality = DownloadQuality.fast, 
                      title: str = None) -> AudioDownloadResult:
        """
        下载音频文件
        
        Args:
            url: 文件URL或路径 (如: baidu_pan://file/path/to/audio.mp3 或 /path/to/audio.mp3)
            download_path: 下载路径
            quality: 下载质量
            title: 自定义标题
            
        Returns:
            AudioDownloadResult: 下载结果
        """
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        try:
            # 解析URL获取远程路径
            remote_path = self._parse_url_to_path(url)
            if not remote_path:
                raise ValueError(f"无效的URL格式: {url}")
            
            logger.info(f"🎵 开始下载音频: {remote_path}")
            
            # 生成本地文件名
            if title:
                clean_title = smart_title_clean(title)
                ext = Path(remote_path).suffix
                local_filename = f"{clean_title}{ext}"
            else:
                local_filename = Path(remote_path).name
            
            local_path = os.path.join(download_path, local_filename)
            
            # 下载文件
            result = self.pcs_service.download_file(remote_path, local_path)
            
            if result.get("success", False) and os.path.exists(local_path):
                file_size = os.path.getsize(local_path)
                return AudioDownloadResult(
                    success=True,
                    file_path=local_path,
                    title=title or Path(local_filename).stem,
                    duration=0,  # BaiduPCS-Py可能不提供时长信息
                    file_size=file_size,
                    format=Path(local_filename).suffix[1:] if Path(local_filename).suffix else "unknown"
                )
            else:
                error_msg = result.get("message", "下载失败")
                return AudioDownloadResult(
                    success=False,
                    error=error_msg
                )
                
        except Exception as e:
            logger.error(f"❌ 下载音频失败: {e}")
            return AudioDownloadResult(
                success=False,
                error=str(e)
            )
    
    def download_video(self, url: str, download_path: str, 
                      quality: DownloadQuality = DownloadQuality.fast, 
                      title: str = None) -> AudioDownloadResult:
        """
        下载视频文件
        """
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        try:
            # 解析URL获取远程路径
            remote_path = self._parse_url_to_path(url)
            if not remote_path:
                raise ValueError(f"无效的URL格式: {url}")
            
            logger.info(f"🎬 开始下载视频: {remote_path}")
            
            # 生成本地文件名
            if title:
                clean_title = smart_title_clean(title)
                ext = Path(remote_path).suffix
                local_filename = f"{clean_title}{ext}"
            else:
                local_filename = Path(remote_path).name
            
            local_path = os.path.join(download_path, local_filename)
            
            # 下载文件
            result = self.pcs_service.download_file(remote_path, local_path)
            
            if result.get("success", False) and os.path.exists(local_path):
                file_size = os.path.getsize(local_path)
                return AudioDownloadResult(  # 复用AudioDownloadResult
                    success=True,
                    file_path=local_path,
                    title=title or Path(local_filename).stem,
                    duration=0,
                    file_size=file_size,
                    format=Path(local_filename).suffix[1:] if Path(local_filename).suffix else "unknown"
                )
            else:
                error_msg = result.get("message", "下载失败")
                return AudioDownloadResult(
                    success=False,
                    error=error_msg
                )
                
        except Exception as e:
            logger.error(f"❌ 下载视频失败: {e}")
            return AudioDownloadResult(
                success=False,
                error=str(e)
            )
    
    def _parse_url_to_path(self, url: str) -> Optional[str]:
        """解析URL到文件路径"""
        try:
            # 处理baidu_pan://协议
            if url.startswith("baidu_pan://file/"):
                return url.replace("baidu_pan://file", "")
            elif url.startswith("baidu_pan://"):
                return url.replace("baidu_pan://", "/")
            # 直接路径
            elif url.startswith("/"):
                return url
            else:
                return None
        except Exception as e:
            logger.error(f"❌ 解析URL失败: {e}")
            return None
    
    def get_video_info(self, url: str) -> Dict[str, any]:
        """获取视频信息"""
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        try:
            remote_path = self._parse_url_to_path(url)
            if not remote_path:
                return {"error": "无效的URL格式"}
            
            # 获取文件信息（通过文件列表）
            parent_path = str(Path(remote_path).parent)
            file_name = Path(remote_path).name
            
            result = self.pcs_service.get_file_list(parent_path)
            if not result.get("success", False):
                return {"error": "获取文件信息失败"}
            
            files = result.get("files", [])
            target_file = None
            for file_info in files:
                if file_info.get("filename") == file_name:
                    target_file = file_info
                    break
            
            if not target_file:
                return {"error": "文件不存在"}
            
            return {
                "title": Path(target_file.get("filename", "")).stem,
                "filename": target_file.get("filename", ""),
                "size": target_file.get("size", 0),
                "size_readable": target_file.get("size_readable", ""),
                "path": target_file.get("path", remote_path),
                "is_media": target_file.get("is_media", False),
                "is_dir": target_file.get("is_dir", False)
            }
            
        except Exception as e:
            logger.error(f"❌ 获取视频信息失败: {e}")
            return {"error": str(e)}
    
    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """上传文件到百度网盘"""
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        result = self.pcs_service.upload_file(local_path, remote_path)
        return result.get("success", False)
    
    def create_download_task(self, files: List[Dict[str, any]], task_config: Dict[str, any]) -> List[Dict[str, any]]:
        """创建下载任务"""
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        tasks = []
        for file_info in files:
            try:
                # 构建任务信息
                task = {
                    "id": f"baidupcs_{file_info.get('fs_id', file_info.get('filename', ''))}",
                    "filename": file_info.get('filename', ''),
                    "path": file_info.get('path', ''),
                    "size": file_info.get('size', 0),
                    "size_readable": file_info.get('size_readable', ''),
                    "is_media": file_info.get('is_media', False),
                    "status": "pending",
                    "progress": 0.0,
                    "download_url": f"baidu_pan://file{file_info.get('path', '')}",
                    "local_path": None,
                    "error": None
                }
                tasks.append(task)
                
            except Exception as e:
                logger.error(f"❌ 创建任务失败: {e}")
                continue
        
        logger.info(f"✅ 创建了 {len(tasks)} 个下载任务")
        return tasks
    
    def download(self, video_url: str, output_dir: str = None, 
                 quality: DownloadQuality = DownloadQuality.fast, 
                 need_video: Optional[bool] = False) -> AudioDownloadResult:
        """
        主下载方法 - 实现抽象基类要求的方法
        
        Args:
            video_url: 文件URL或路径 (如: baidu_pan://file/path/to/audio.mp3 或 /path/to/audio.mp3)
            output_dir: 下载路径
            quality: 下载质量
            need_video: 是否需要视频文件
            
        Returns:
            AudioDownloadResult: 下载结果
        """
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        try:
            # 解析URL获取远程路径
            remote_path = self._parse_url_to_path(video_url)
            if not remote_path:
                raise ValueError(f"无效的URL格式: {video_url}")
            
            logger.info(f"🎯 开始下载文件: {remote_path}")
            
            # 根据文件类型选择下载方法
            ext = Path(remote_path).suffix.lower()
            title = Path(remote_path).stem
            
            if ext in self.audio_extensions:
                return self.download_audio(video_url, output_dir, quality, title)
            elif ext in self.video_extensions:
                result = self.download_video(video_url, output_dir, quality, title)
                # 如果需要视频文件，设置video_path
                if need_video and result.success:
                    result.video_path = result.file_path
                return result
            else:
                # 其他文件类型也支持下载
                return self.download_audio(video_url, output_dir, quality, title)
                
        except Exception as e:
            logger.error(f"❌ 下载文件失败: {e}")
            return AudioDownloadResult(
                success=False,
                error=str(e)
            ) 