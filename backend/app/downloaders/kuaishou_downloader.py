import os
import subprocess
from abc import ABC
from typing import Union, Optional

import requests

from app.downloaders.base import Downloader
from app.downloaders.kuaishou_helper.kuaishou import KuaiShou
from app.enmus.note_enums import DownloadQuality
from app.models.audio_model import AudioDownloadResult
from app.utils.path_helper import get_data_dir
from app.utils.title_cleaner import smart_title_clean
from app.utils.logger import get_logger

logger = get_logger(__name__)


class KuaiShouDownloader(Downloader, ABC):
    def __init__(self):
        super().__init__()

    def download(
            self,
            video_url: str,
            output_dir: Union[str, None] = None,
            quality: str = "fast",
            need_video: Optional[bool] = False
    ) -> AudioDownloadResult:
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir = self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        ks = KuaiShou()
        video_raw_info = ks.run(video_url)
        print(video_raw_info)
        photo_info = video_raw_info['visionVideoDetail']['photo']
        video_id = photo_info['id']
        original_title = photo_info['caption'].strip().replace('\n', '').replace(' ', '_')[:50]
        mp4_path = os.path.join(output_dir, f"{video_id}.mp4")
        mp3_path = os.path.join(output_dir, f"{video_id}.mp3")

        # 🧹 清理标题，去掉合集相关字符串
        cleaned_title = smart_title_clean(original_title, platform="kuaishou", preserve_episode=False)
        logger.info(f"🧹 快手标题清理: '{original_title}' -> '{cleaned_title}'")

        if os.path.exists(mp3_path):
            print(f"[已存在] 跳过下载: {mp3_path}")
            return AudioDownloadResult(
                file_path=mp3_path,
                title=cleaned_title,  # 使用清理后的标题
                duration=photo_info['duration'],
                cover_url=photo_info['coverUrl'],
                platform="kuaishou",
                video_id=video_id,
                raw_info={
                    'tags': ','.join(tag['name'] for tag in video_raw_info.get('tags', []) if tag.get('name'))
                },
                video_path=mp4_path
            )

        # 下载 mp4 视频
        resp = requests.get(photo_info['photoUrl'], stream=True)
        if resp.status_code == 200:
            with open(mp4_path, "wb") as f:
                for chunk in resp.iter_content(1024 * 1024):
                    f.write(chunk)
        else:
            raise Exception(f"视频下载失败: {resp.status_code}")

        # 使用 ffmpeg 转换为 mp3
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", mp4_path, "-vn", "-acodec", "libmp3lame", mp3_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            raise Exception("ffmpeg 转换 MP3 失败")

        return AudioDownloadResult(
            file_path=mp3_path,
            title=cleaned_title,  # 使用清理后的标题
            duration=photo_info['duration'],
            cover_url=photo_info['coverUrl'],
            platform="kuaishou",
            video_id=video_id,
            raw_info={
                'tags': ','.join(tag['name'] for tag in video_raw_info.get('tags', []) if tag.get('name'))
            },
            video_path=mp4_path
        )

    def download_video(
            self,
            video_url: str,
            output_dir: Union[str, None] = None,
    ) -> str:
        print('self.download(video_url, output_dir).video_path',self.download(video_url, output_dir).video_path)
        return self.download(video_url, output_dir).video_path


if __name__ == '__main__':
    ks = KuaiShouDownloader()
    ks.download('https://v.kuaishou.com/2vBqX74 王宝强携手刘昊然、岳云鹏上演精彩名场面 全程高能 看一遍笑一遍 "唐探1900 "快成长计划 ...更多')