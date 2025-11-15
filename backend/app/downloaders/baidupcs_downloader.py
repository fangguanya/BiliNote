#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一的百度网盘下载器
基于BaiduPCS-Py命令行工具，支持baidu_pan://协议
通过全局下载管理器确保串行下载
"""

import os
import re
from typing import Optional, List, Dict, Union, Tuple
from pathlib import Path
from urllib.parse import unquote

from app.downloaders.base import Downloader, DownloadQuality, QUALITY_MAP
from app.models.notes_model import AudioDownloadResult
from app.third_party.baidupcs_api import BaiduPCSDownloader as BaiduPCSApiDownloader
from app.services.global_download_manager import global_download_manager
from app.exceptions.auth_exceptions import AuthRequiredException
from app.utils.logger import get_logger
from app.utils.title_cleaner import smart_title_clean
from app.utils.path_helper import get_data_dir

logger = get_logger(__name__)


class BaiduPCSDownloader(Downloader):
    """
    统一的百度网盘下载器
    直接使用 BaiduPCS Python API，支持baidu_pan://协议和多种链接格式
    通过全局下载管理器确保串行下载
    """
    
    def __init__(self):
        super().__init__()
        # 使用 API 下载器（直接调用 Python API，不再使用命令行工具）
        self.api_downloader = BaiduPCSApiDownloader()
        
        # 支持的视频和音频格式
        self.video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.m2ts', '.f4v', '.rmvb', '.rm'}
        self.audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.ape', '.ac3', '.dts'}
        
        logger.info("🔧 统一百度网盘下载器初始化完成（使用全局下载管理器）")
    
    # =============== 用户管理 ===============
    
    def add_user(self, cookies: str, bduss: str = None) -> bool:
        """添加百度网盘用户"""
        if cookies:
            result = self.api_downloader.add_user_by_cookies(cookies)
        elif bduss:
            result = self.api_downloader.add_user_by_bduss(bduss)
        else:
            return False
        
        return result.get("success", False)
    
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return self.api_downloader.is_authenticated()
    
    # =============== 文件管理 ===============
    
    def get_file_list(self, path: str = "/", share_code: str = None, extract_code: str = None, 
                      use_cache: bool = True, recursive: bool = False) -> List[Dict[str, any]]:
        """
        获取文件列表
        
        Args:
            path: 目录路径
            share_code: 分享码（暂不支持）
            extract_code: 提取码（暂不支持）
            use_cache: 是否使用缓存（默认True，可大幅提高性能）
            recursive: 是否递归获取子目录（默认False）
        """
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        # 目前不支持分享链接，只支持个人文件
        if share_code or extract_code:
            logger.warning("⚠️ 当前版本不支持分享链接，只能获取个人文件列表")
        
        # 🚀 使用优化后的API，支持缓存
        result = self.api_downloader.list_files(path, recursive=recursive, use_cache=use_cache)
        if result.get("success", False):
            return result.get("files", [])
        return []
    
    def get_current_user_info(self) -> Dict[str, any]:
        """获取当前用户信息"""
        if not self.is_authenticated():
            return {}
        
        user_info_result = self.api_downloader.get_user_info()
        if user_info_result.get("success", False):
            return {
                "user_id": user_info_result.get("user_id"),
                "user_name": user_info_result.get("user_name"),
                "quota": user_info_result.get("quota"),
                "used": user_info_result.get("used")
            }
        
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
                    # ⚠️ 关键修复：清理文件名中的换行符和多余空格
                    filename = filename.replace('\n', '').replace('\r', '').replace('\t', '')
                    logger.debug(f"🔍 解析后的filename: {repr(filename)}")
                if file_path:
                    original_path = file_path
                    file_path = urllib.parse.unquote(file_path)
                    # ⚠️ 关键修复：清理路径中的换行符和多余空格
                    file_path = file_path.replace('\n', '').replace('\r', '').replace('\t', '')
                    logger.info(f"🔍 URL解析 - 原始path参数: {repr(original_path)}")
                    logger.info(f"🔍 URL解析 - unquote后: {repr(urllib.parse.unquote(original_path))}")
                    logger.info(f"🔍 URL解析 - 清理后的file_path: {repr(file_path)}")
                
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
    
    def _download_file_internal(self, url: str, download_path: str, 
                               quality: DownloadQuality, title: str = None, 
                               file_type: str = "file") -> AudioDownloadResult:
        """内部下载方法 - 不通过全局管理器"""
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
            
            logger.info(f"🔧 调用 BaiduPCS API 下载器")
            logger.info(f"   远程路径: {remote_path}")
            logger.info(f"   本地目录: {download_path}")
            logger.info(f"   本地文件名: {local_filename}")
            logger.info(f"   下载质量: {quality}")
            
            # 🚀 根据质量参数调整并发数和块大小，大幅提高下载速度
            if quality == DownloadQuality.fast:
                concurrency = 32  # 大幅提高并发数
                chunk_size = 10 * 1024 * 1024  # 10MB，更大的块减少请求次数
            elif quality == DownloadQuality.medium:
                concurrency = 64  # 更高并发
                chunk_size = 20 * 1024 * 1024  # 20MB
            else:  # slow or original
                concurrency = 128  # 最高并发，适合大文件
                chunk_size = 30 * 1024 * 1024  # 30MB（接近50MB上限）
            
            logger.info(f"   并发数: {concurrency}, 块大小: {chunk_size // 1024 // 1024}MB")
            
            # 直接使用 API 下载器
            result = self.api_downloader.download_file(
                remote_path=remote_path,
                local_dir=download_path,
                local_filename=local_filename,
                concurrency=concurrency,
                chunk_size=chunk_size
            )
            
            logger.info(f"🔍 API 下载器返回结果:")
            logger.info(f"   结果类型: {type(result)}")
            logger.info(f"   结果内容: {result}")
            logger.info(f"   success值: {result.get('success', 'N/A')}")
            
            # API 下载器返回的是 'local_path' 字段
            actual_local_path = result.get('local_path', local_path)
            
            if result.get("success", False) and os.path.exists(actual_local_path):
                file_size = os.path.getsize(actual_local_path)
                
                logger.info(f"✅ {file_type}下载成功: {actual_local_path}")
                logger.info(f"📏 文件大小: {file_size} 字节")
                
                download_result = AudioDownloadResult(
                    file_path=actual_local_path,
                    title=title or Path(local_filename).stem,
                    duration=0,  # BaiduPCS-Py可能不提供时长信息
                    cover_url=None,
                    platform="baidu_pan",
                    video_id=Path(local_filename).stem,
                    raw_info={
                        "file_size": file_size,
                        "format": Path(local_filename).suffix[1:] if Path(local_filename).suffix else "unknown",
                        "remote_path": remote_path,
                        "download_method": "baidupcs_api"
                    },
                    video_path=actual_local_path if file_type == "video" else None
                )
                
                logger.info(f"🎉 创建AudioDownloadResult对象:")
                logger.info(f"   类型: {type(download_result)}")
                logger.info(f"   文件路径: {download_result.file_path}")
                logger.info(f"   标题: {download_result.title}")
                logger.info(f"   平台: {download_result.platform}")
                
                return download_result
            else:
                error_msg = result.get("message", "下载失败")
                logger.error(f"❌ {file_type}下载失败: {error_msg}")
                logger.error(f"   BaiduPCS结果success: {result.get('success', 'N/A')}")
                logger.error(f"   文件存在: {os.path.exists(local_path)}")
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"❌ 下载{file_type}失败: {e}")
            logger.error(f"   异常类型: {type(e)}")
            raise e

    def _download_file(self, url: str, download_path: str, 
                      quality: DownloadQuality, title: str = None, 
                      file_type: str = "file") -> AudioDownloadResult:
        """统一的文件下载方法 - 通过全局下载管理器"""
        if not self.is_authenticated():
            raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
        
        try:
            # 解析URL获取远程路径
            remote_path = self._parse_url_to_path(url)
            if not remote_path:
                raise ValueError(f"无效的URL格式: {url}")
            
            # 🔧 关键修复：生成简化的本地文件名，避免Windows 260字符路径限制
            import hashlib
            
            if title:
                clean_title = smart_title_clean(title)
                ext = Path(remote_path).suffix
                local_filename = f"{clean_title}{ext}"
            else:
                original_filename = Path(remote_path).name
                ext = Path(remote_path).suffix
                base_name = Path(remote_path).stem
                
                # 如果文件名太长，简化它
                # Windows完整路径限制是260字符，我们确保文件名不超过100字符
                max_filename_length = 100
                if len(original_filename) > max_filename_length:
                    # 使用文件名前缀 + 哈希值 + 扩展名
                    # 前缀取前50个字符，确保可读性
                    prefix_length = 50
                    prefix = base_name[:prefix_length] if len(base_name) > prefix_length else base_name
                    
                    # 使用完整文件名的MD5哈希值（取前8位）
                    hash_value = hashlib.md5(original_filename.encode('utf-8')).hexdigest()[:8]
                    
                    local_filename = f"{prefix}_{hash_value}{ext}"
                    logger.info(f"🔧 简化本地文件名:")
                    logger.info(f"   原始文件名: {original_filename}")
                    logger.info(f"   简化文件名: {local_filename}")
                else:
                    local_filename = original_filename
            
            local_path = os.path.join(download_path, local_filename)
            
            logger.info(f"🌍 通过全局下载管理器下载: {remote_path}")
            
            # 通过全局下载管理器执行下载
            task_id = global_download_manager.add_download_task(
                "baidu_pan", url, local_path, self._download_file_internal,
                url, download_path, quality, title, file_type
            )
            
            # 等待下载完成
            result = global_download_manager.wait_for_completion(task_id, timeout=1800)
            
            if result.get("success", False):
                download_result = result.get("result")
                if download_result:
                    return download_result
                else:
                    # 如果没有返回AudioDownloadResult，创建一个
                    return AudioDownloadResult(
                        file_path=local_path,
                        title=title or Path(local_filename).stem,
                        duration=0,
                        cover_url=None,
                        platform="baidu_pan",
                        video_id=Path(local_filename).stem,
                        raw_info={"download_method": "global_manager"},
                        video_path=local_path if file_type == "video" else None
                    )
            else:
                error_msg = result.get("message", "下载失败")
                logger.error(f"❌ 全局下载管理器下载失败: {error_msg}")
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
            
            result = self.api_downloader.list_files(parent_path)
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
        
        result = self.api_downloader.upload_file(local_path, remote_path)
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