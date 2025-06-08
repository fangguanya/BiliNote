import os
import re
from abc import ABC
from typing import Union, Optional

import yt_dlp
import requests

from app.downloaders.base import Downloader, DownloadQuality, QUALITY_MAP
from app.models.notes_model import AudioDownloadResult
from app.utils.path_helper import get_data_dir
from app.utils.url_parser import extract_video_id
from app.services.cookie_manager import CookieConfigManager
from app.exceptions.auth_exceptions import AuthRequiredException
from app.utils.logger import get_logger
from app.utils.title_cleaner import smart_title_clean

logger = get_logger(__name__)


class BilibiliDownloader(Downloader, ABC):
    def __init__(self):
        super().__init__()
        self.cookie_manager = CookieConfigManager()

    def _get_multipart_title_from_api(self, video_url: str) -> Optional[str]:
        """
        通过API获取分P视频的准确标题
        """
        try:
            # 解析URL获取BV号和分P号
            bv_match = re.search(r'BV([0-9A-Za-z]+)', video_url)
            p_match = re.search(r'[?&]p=(\d+)', video_url)
            
            if not bv_match:
                return None
                
            bv_id = f'BV{bv_match.group(1)}'
            page_num = int(p_match.group(1)) if p_match else 1
            
            logger.info(f"📺 获取分P视频标题: {bv_id} P{page_num}")
            
            # 调用B站API
            api_url = f'https://api.bilibili.com/x/web-interface/view?bvid={bv_id}'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com/'
            }
            
            # 添加cookie支持
            cookie = self.cookie_manager.get("bilibili")
            if cookie:
                headers['Cookie'] = cookie
            
            response = requests.get(api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0 and 'data' in data:
                    video_data = data['data']
                    
                    # 检查是否有分P信息
                    if 'pages' in video_data:
                        pages = video_data['pages']
                        
                        # 查找对应的分P
                        for page in pages:
                            if page.get('page') == page_num:
                                part_title = page.get('part', '').strip()
                                logger.info(f"✅ 从API获取到P{page_num}标题: '{part_title}'")
                                return part_title
                        
                        # 如果找不到指定分P，返回第一个分P的标题
                        if pages and page_num > len(pages):
                            first_page = pages[0]
                            part_title = first_page.get('part', '').strip()
                            logger.warning(f"⚠️ P{page_num}不存在，使用P1标题: '{part_title}'")
                            return part_title
                    else:
                        # 单P视频，返回视频标题
                        video_title = video_data.get('title', '').strip()
                        logger.info(f"✅ 单P视频标题: '{video_title}'")
                        return video_title
                        
        except Exception as e:
            logger.warning(f"⚠️ API获取分P标题失败: {e}")
            
        return None

    def _get_ydl_opts(self, output_path: str, format_selector: str = 'bestaudio[ext=m4a]/bestaudio/best'):
        """获取yt-dlp配置"""
        opts = {
            'format': format_selector,
            'outtmpl': output_path,
            'noplaylist': True,
            'quiet': False,
        }
        
        # 添加cookie配置
        cookie = self.cookie_manager.get("bilibili")
        if cookie:
            logger.info("🍪 使用已保存的B站cookie")
            opts['cookiefile'] = None  # 不使用文件
            opts['cookies'] = cookie
        
        return opts

    def _check_auth_required(self, error_message: str) -> bool:
        """检查错误信息是否表示需要认证"""
        auth_keywords = [
            "需要登录",
            "登录",
            "cookie",
            "authentication",
            "premium member",
            "会员",
            "大会员"
        ]
        
        error_lower = error_message.lower()
        return any(keyword in error_lower for keyword in auth_keywords)

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video: Optional[bool] = False
    ) -> AudioDownloadResult:
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir = self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = self._get_ydl_opts(output_path)
        ydl_opts['postprocessors'] = [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '64',
            }
        ]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_id = info.get("id")
                original_title = info.get("title")
                duration = info.get("duration", 0)
                cover_url = info.get("thumbnail")
                audio_path = os.path.join(output_dir, f"{video_id}.mp3")

            # 🎯 针对分P视频的特殊处理
            final_title = original_title
            
            # 检查是否为分P视频URL
            if 'p=' in video_url:
                # 尝试从API获取准确的分P标题
                api_title = self._get_multipart_title_from_api(video_url)
                if api_title:
                    final_title = api_title
                    logger.info(f"🎯 使用API获取的分P标题: '{final_title}'")
                else:
                    # API失败，使用智能清理
                    final_title = smart_title_clean(original_title, platform="bilibili", preserve_episode=False)
                    logger.info(f"🧹 API失败，使用智能清理: '{original_title}' -> '{final_title}'")
            else:
                # 非分P视频，使用智能清理
                final_title = smart_title_clean(original_title, platform="bilibili", preserve_episode=False)
                logger.info(f"🧹 普通视频标题清理: '{original_title}' -> '{final_title}'")

            return AudioDownloadResult(
                file_path=audio_path,
                title=final_title,  # 使用处理后的标题
                duration=duration,
                cover_url=cover_url,
                platform="bilibili",
                video_id=video_id,
                raw_info=info,
                video_path=None  # ❗音频下载不包含视频路径
            )
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"❌ B站下载失败: {error_message}")
            
            # 检查是否需要认证
            if self._check_auth_required(error_message):
                logger.warning("⚠️ 检测到需要B站登录认证")
                raise AuthRequiredException(
                    platform="bilibili",
                    message="该视频需要B站登录认证，请先扫码登录"
                )
            else:
                # 其他错误直接抛出
                raise e

    def download_video(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
    ) -> str:
        """
        下载视频，返回视频文件路径
        """

        if output_dir is None:
            output_dir = get_data_dir()
        os.makedirs(output_dir, exist_ok=True)
        print("video_url", video_url)
        video_id = extract_video_id(video_url, "bilibili")
        video_path = os.path.join(output_dir, f"{video_id}.mp4")
        if os.path.exists(video_path):
            return video_path

        # 检查是否已经存在
        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = self._get_ydl_opts(
            output_path, 
            'bv*[ext=mp4]/bestvideo+bestaudio/best'
        )
        ydl_opts['merge_output_format'] = 'mp4'  # 确保合并成 mp4

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_id = info.get("id")
                video_path = os.path.join(output_dir, f"{video_id}.mp4")

            if not os.path.exists(video_path):
                raise FileNotFoundError(f"视频文件未找到: {video_path}")

            return video_path
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"❌ B站视频下载失败: {error_message}")
            
            # 检查是否需要认证
            if self._check_auth_required(error_message):
                logger.warning("⚠️ 检测到需要B站登录认证")
                raise AuthRequiredException(
                    platform="bilibili",
                    message="该视频需要B站登录认证，请先扫码登录"
                )
            else:
                # 其他错误直接抛出
                raise e

    def delete_video(self, video_path: str) -> str:
        """
        删除视频文件
        """
        if os.path.exists(video_path):
            os.remove(video_path)
            return f"视频文件已删除: {video_path}"
        else:
            return f"视频文件未找到: {video_path}"