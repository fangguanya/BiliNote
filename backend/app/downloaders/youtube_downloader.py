import os
from abc import ABC
from typing import Union, Optional

import yt_dlp

from app.downloaders.base import Downloader, DownloadQuality
from app.models.notes_model import AudioDownloadResult
from app.utils.path_helper import get_data_dir
from app.utils.url_parser import extract_video_id
from app.utils.title_cleaner import smart_title_clean
from app.utils.logger import get_logger

logger = get_logger(__name__)


class YoutubeDownloader(Downloader, ABC):
    def __init__(self):

        super().__init__()

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video:Optional[bool]=False
    ) -> AudioDownloadResult:
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir=self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            #'format': 'bestaudio[ext=m4a]/bestaudio/best',
            # 修改：使用更灵活的格式选择，避免某些视频格式不可用的问题
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_path,
            'noplaylist': False,  # 修改：允许下载播放列表
            'no_warnings': False,
            'extract_flat': False,
            'quiet': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            original_title = info.get("title")
            duration = info.get("duration", 0)
            cover_url = info.get("thumbnail")
            ext = info.get("ext", "m4a")  # 兜底用 m4a
            audio_path = os.path.join(output_dir, f"{video_id}.{ext}")
        print('os.path.join(output_dir, f"{video_id}.{ext}")',os.path.join(output_dir, f"{video_id}.{ext}"))

        # 🧹 清理标题，去掉合集相关字符串  
        cleaned_title = smart_title_clean(original_title, platform="youtube", preserve_episode=False)
        logger.info(f"🧹 YouTube标题清理: '{original_title}' -> '{cleaned_title}'")

        return AudioDownloadResult(
            file_path=audio_path,
            title=cleaned_title,  # 使用清理后的标题
            duration=duration,
            cover_url=cover_url,
            platform="youtube",
            video_id=video_id,
            raw_info={'tags':info.get('tags')}, #全部返回会报错
            video_path=None  # ❗音频下载不包含视频路径
        )

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
        output_template = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            # 修改：使用更灵活的格式选择
            # 优先下载mp4格式的视频，如果不可用则自动选择最佳可用格式
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best',
            'outtmpl': output_template,
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'merge_output_format': 'mp4',  # 合并后的格式为mp4
        }

        actual_video_path = None
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 提取信息并下载
            info = ydl.extract_info(video_url, download=True)
            
            # 使用 yt-dlp 的 prepare_filename 方法获取实际文件路径
            actual_video_path = ydl.prepare_filename(info)
            
            # 如果文件有后缀处理（如合并后），需要替换扩展名
            if 'ext' in info:
                base_path = os.path.splitext(actual_video_path)[0]
                actual_video_path = f"{base_path}.{info['ext']}"

        # 检查文件是否存在
        if not os.path.exists(actual_video_path):
            raise FileNotFoundError(f"视频文件未找到: {actual_video_path}")

        return actual_video_path


    def download_video1(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
    ) -> str:
        """
        下载视频，返回视频文件路径
        """
        if output_dir is None:
            output_dir = get_data_dir()
        video_id = extract_video_id(video_url, "youtube")
        #video_path = os.path.join(output_dir, f"{video_id}.mp4")
        #if os.path.exists(video_path):
        #    return video_path
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            #'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
            'format': 'best[ext=mp4]/best',
            'outtmpl': output_path,
            #'noplaylist': True,
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            #video_path = os.path.join(output_dir, f"{video_id}.mp4")

        if not os.path.exists(output_path):
            raise FileNotFoundError(f"视频文件未找到: {output_path}")

        return output_path
