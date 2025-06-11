#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一的百度网盘下载器
基于BaiduPCS-Py命令行工具，支持baidu_pan://协议
"""

import os
import re
from typing import Optional, List, Dict, Union, Tuple
from pathlib import Path
from urllib.parse import unquote

from app.downloaders.base import Downloader, DownloadQuality, QUALITY_MAP
from app.models.notes_model import AudioDownloadResult
from app.services.baidupcs_service import baidupcs_service
from app.exceptions.auth_exceptions import AuthRequiredException
from app.utils.logger import get_logger
from app.utils.title_cleaner import smart_title_clean
from app.utils.path_helper import get_data_dir

logger = get_logger(__name__)


class BaiduPCSDownloader(Downloader):
    """
    统一的百度网盘下载器
    基于BaiduPCS-Py命令行工具，支持baidu_pan://协议和多种链接格式
    """
    
    def __init__(self):
        super().__init__()
        self.pcs_service = baidupcs_service
        
        # 支持的视频和音频格式
        self.video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.m2ts', '.f4v', '.rmvb', '.rm'}
        self.audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.ape', '.ac3', '.dts'}
        
        logger.info("🔧 统一百度网盘下载器初始化完成")
    
    # =============== 用户管理 ===============
    
    def add_user(self, cookies: str, bduss: str = None) -> bool:
        """添加百度网盘用户"""
        if cookies:
            result = self.pcs_service.add_user_by_cookies(cookies)
        elif bduss:
            result = self.pcs_service.add_user_by_bduss(bduss)
        else:
            return False
        
        return result.get("success", False)
    
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return self.pcs_service.is_authenticated()
    
    # =============== 文件管理 ===============
    
    def get_file_list(self, path: str = "/", share_code: str = None, extract_code: str = None) -> List[Dict[str, any]]:
        """获取文件列表"""
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        # 目前不支持分享链接，只支持个人文件
        if share_code or extract_code:
            logger.warning("⚠️ 当前版本不支持分享链接，只能获取个人文件列表")
        
        result = self.pcs_service.get_file_list(path)
        if result.get("success", False):
            return result.get("files", [])
        return []
    
    def get_current_user_info(self) -> Dict[str, any]:
        """获取当前用户信息"""
        if not self.is_authenticated():
            return {}
        
        user_info_result = self.pcs_service.get_user_info()
        if user_info_result.get("success", False):
            raw_info = user_info_result.get("info", "")
            parsed_info = self.pcs_service._parse_user_info(raw_info)
            return parsed_info
        
        return {}
    
    # =============== URL解析 ===============
    
    def parse_baidu_pan_url(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        解析baidu_pan://协议URL
        返回: (fs_id, filename, file_path)
        """
        try:
            if not url.startswith("baidu_pan://file/"):
                return None, None, None
            
            # baidu_pan://file/867486328653516?filename=xxx.mp4&path=/path/to/file.mp4
            import urllib.parse
            
            # 移除协议头
            url_part = url.replace("baidu_pan://file/", "")
            
            # 分离fs_id和查询参数
            if "?" in url_part:
                fs_id, query_string = url_part.split("?", 1)
                query_params = urllib.parse.parse_qs(query_string)
                
                filename = query_params.get("filename", [None])[0]
                file_path = query_params.get("path", [None])[0]
                
                if filename:
                    filename = urllib.parse.unquote(filename)
                if file_path:
                    file_path = urllib.parse.unquote(file_path)
                
                return fs_id, filename, file_path
            else:
                return url_part, None, None
                
        except Exception as e:
            logger.error(f"❌ 解析baidu_pan URL失败: {e}")
            return None, None, None
    
    def can_download(self, url: str) -> bool:
        """检查是否可以下载该URL"""
        # 支持百度网盘路径和fs_id
        if url.startswith("baidu_pan://"):
            return True
        
        # 支持网盘路径
        if url.startswith("/") and self.is_authenticated():
            return True
        
        return False
    
    def _parse_url_to_path(self, url: str) -> Optional[str]:
        """解析URL到文件路径"""
        try:
            # 处理baidu_pan://协议
            if url.startswith("baidu_pan://file/"):
                # 从baidu_pan协议中提取实际的文件路径
                fs_id, filename, file_path = self.parse_baidu_pan_url(url)
                if file_path:
                    # 优先使用path参数中的完整路径
                    return file_path
                elif filename:
                    # 如果没有path，使用根目录+文件名
                    return f"/{filename}"
                else:
                    # 最后使用fs_id作为路径（可能不工作）
                    logger.warning(f"⚠️ baidu_pan协议缺少路径信息，尝试使用fs_id: {fs_id}")
                    return f"/{fs_id}"
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
    
    # =============== 下载功能 ===============
    
    def download_audio(self, url: str, download_path: str, 
                      quality: DownloadQuality = DownloadQuality.fast, 
                      title: str = None, use_chunked_download: bool = None) -> AudioDownloadResult:
        """下载音频文件"""
        return self._download_file(url, download_path, quality, title, "audio")
    
    def download_video(self, url: str, download_path: str, 
                      quality: DownloadQuality = DownloadQuality.fast, 
                      title: str = None, use_chunked_download: bool = None) -> AudioDownloadResult:
        """下载视频文件"""
        return self._download_file(url, download_path, quality, title, "video")
    
    def _download_file(self, url: str, download_path: str, 
                      quality: DownloadQuality, title: str = None, 
                      file_type: str = "file") -> AudioDownloadResult:
        """统一的文件下载方法"""
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        try:
            # 解析URL获取远程路径
            remote_path = self._parse_url_to_path(url)
            if not remote_path:
                raise ValueError(f"无效的URL格式: {url}")
            
            logger.info(f"🎯 开始下载{file_type}: {remote_path}")
            
            # 生成本地文件名
            if title:
                clean_title = smart_title_clean(title)
                ext = Path(remote_path).suffix
                local_filename = f"{clean_title}{ext}"
            else:
                local_filename = Path(remote_path).name
            
            local_path = os.path.join(download_path, local_filename)
            
            # 使用BaiduPCS服务下载
            result = self.pcs_service.download_file(
                remote_path=remote_path, 
                local_path=local_path,
                downloader="me",  # 使用推荐的me下载器
                concurrency=5     # 5个并发连接
            )
            
            if result.get("success", False) and os.path.exists(local_path):
                file_size = os.path.getsize(local_path)
                
                logger.info(f"✅ {file_type}下载成功: {local_path}")
                
                return AudioDownloadResult(
                    file_path=local_path,
                    title=title or Path(local_filename).stem,
                    duration=0,  # BaiduPCS-Py可能不提供时长信息
                    cover_url=None,
                    platform="baidu_pan",
                    video_id=Path(local_filename).stem,
                    raw_info={
                        "file_size": file_size,
                        "format": Path(local_filename).suffix[1:] if Path(local_filename).suffix else "unknown",
                        "remote_path": remote_path,
                        "download_method": "baidupcs"
                    },
                    video_path=local_path if file_type == "video" else None
                )
            else:
                error_msg = result.get("message", "下载失败")
                logger.error(f"❌ {file_type}下载失败: {error_msg}")
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"❌ 下载{file_type}失败: {e}")
            raise e
    
    # =============== 主下载方法 ===============
    
    def download(self, video_url: str, output_dir: str = None, 
                 quality: DownloadQuality = DownloadQuality.fast, 
                 need_video: Optional[bool] = False) -> AudioDownloadResult:
        """主下载方法 - 支持多种URL格式"""
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        try:
            if not output_dir:
                output_dir = get_data_dir()
            
            logger.info(f"🎯 开始处理百度网盘链接: {video_url}")
            
            # 检查是否为baidu_pan://协议链接
            fs_id, filename, file_path = self.parse_baidu_pan_url(video_url)
            if fs_id and filename and file_path:
                logger.info(f"🎯 检测到baidu_pan协议链接: fs_id={fs_id}, filename={filename}")
                
                # 直接下载文件（使用解析到的实际路径）
                result = self._download_file(file_path, output_dir, quality, None, "file")
                
                # 获取原始标题并清理
                original_title = os.path.splitext(filename)[0]  # 去掉扩展名作为标题
                
                # 🧹 清理标题，去掉合集相关字符串
                cleaned_title = smart_title_clean(original_title, platform="baidu_pan", preserve_episode=False)
                logger.info(f"🧹 百度网盘标题清理: '{original_title}' -> '{cleaned_title}'")
                
                # 更新返回结果
                result.title = cleaned_title
                result.platform = "baidu_pan"
                result.video_id = fs_id
                result.raw_info.update({
                    "fs_id": fs_id,
                    "filename": filename,
                    "source_url": video_url,
                    "file_path": file_path,
                    "download_method": "baidupcs_direct"
                })
                
                # 如果需要视频文件，设置video_path
                if need_video:
                    result.video_path = result.file_path
                
                return result
            
            else:
                # 解析URL获取远程路径
                remote_path = self._parse_url_to_path(video_url)
                if not remote_path:
                    raise ValueError(f"无效的URL格式: {video_url}")
                
                logger.info(f"🎯 开始下载文件: {remote_path}")
                
                # 根据文件类型选择下载方法
                ext = Path(remote_path).suffix.lower()
                title = Path(remote_path).stem
                
                if ext in self.audio_extensions:
                    result = self.download_audio(video_url, output_dir, quality, title)
                elif ext in self.video_extensions:
                    result = self.download_video(video_url, output_dir, quality, title)
                    # 如果需要视频文件，设置video_path
                    if need_video:
                        result.video_path = result.file_path
                else:
                    # 其他文件类型也支持下载
                    result = self._download_file(video_url, output_dir, quality, title, "file")
                
                return result
                
        except Exception as e:
            logger.error(f"❌ 下载文件失败: {e}")
            raise e
    
    # =============== 其他功能 ===============
    
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
    
    # =============== 静态方法（向后兼容） ===============
    
    @staticmethod  
    def download_video(video_url: str, output_dir: Union[str, None] = None) -> str:
        """
        下载视频文件（静态方法，保持接口兼容性）
        """
        downloader = BaiduPCSDownloader()
        result = downloader.download(video_url, output_dir, need_video=True)
        return result.video_path or result.file_path


# 为了向后兼容，创建一个别名
BaiduPanDownloader = BaiduPCSDownloader 