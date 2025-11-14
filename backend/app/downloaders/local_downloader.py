import os
import subprocess
from abc import ABC
from typing import Optional

from app.downloaders.base import Downloader
from app.enmus.note_enums import DownloadQuality
from app.models.audio_model import AudioDownloadResult
import os
import subprocess

from app.utils.video_helper import save_cover_to_static
from app.utils.title_cleaner import smart_title_clean
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LocalDownloader(Downloader, ABC):
    def __init__(self):

        super().__init__()


    def extract_cover(self, input_path: str, output_dir: Optional[str] = None) -> str:
        """
        从本地视频文件中提取一张封面图（默认取第一帧）
        :param input_path: 输入视频路径
        :param output_dir: 输出目录，默认和视频同目录
        :return: 提取出的封面图片路径
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(output_dir, f"{base_name}_cover.jpg")

        try:
            command = [
                'ffmpeg',
                '-i', input_path,
                '-ss', '00:00:01',  # 跳到视频第1秒，防止黑屏
                '-vframes', '1',  # 只截取一帧
                '-q:v', '2',  # 输出质量高一点（qscale，2是很高）
                '-y',  # 覆盖
                output_path
            ]
            subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, encoding='utf-8', errors='ignore')

            if not os.path.exists(output_path):
                raise RuntimeError(f"封面图片生成失败: {output_path}")

            return output_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"提取封面失败: {output_path}") from e

    def convert_to_mp3(self, input_path: str, output_dir: Optional[str] = None) -> str:
        """
        将输入视频转换为MP3音频
        :param input_path: 输入视频文件路径
        :param output_dir: 输出目录，默认和输入文件同目录
        :return: 输出的MP3文件路径
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        # 生成输出文件名
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(output_dir, f"{base_name}.mp3")

        # 如果MP3文件已存在，直接返回
        if os.path.exists(output_path):
            print(f"MP3文件已存在，跳过转换: {output_path}")
            return output_path

        try:
            # 使用 ffmpeg 转换为 MP3
            command = [
                'ffmpeg',
                '-i', input_path,  # 输入文件
                '-vn',  # 禁用视频流
                '-acodec', 'libmp3lame',  # 使用MP3编码器
                '-b:a', '128k',  # 音频比特率
                '-y',  # 覆盖输出文件
                output_path
            ]

            subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, encoding='utf-8', errors='ignore')

            if not os.path.exists(output_path):
                raise RuntimeError(f"MP3转换失败: {output_path}")

            print(f"MP3转换成功: {input_path} -> {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg 转换失败: {e}")


    def download(
            self,
            video_url: str,
            output_dir: str = None,
            quality: DownloadQuality = "fast",
            need_video: Optional[bool] = False
    ) -> AudioDownloadResult:
        """
        处理本地文件路径，返回音频元信息
        """
        if video_url.startswith('/uploads'):
            project_root = os.getcwd()
            video_url = os.path.join(project_root, video_url.lstrip('/'))
            video_url = os.path.normpath(video_url)

        if not os.path.exists(video_url):
            raise FileNotFoundError(f"本地文件不存在: {video_url}")

        file_name = os.path.basename(video_url)
        original_title, _ = os.path.splitext(file_name)
        
        # 🧹 清理标题，去掉合集相关字符串
        cleaned_title = smart_title_clean(original_title, platform="local", preserve_episode=False)
        logger.info(f"🧹 本地文件标题清理: '{original_title}' -> '{cleaned_title}'")
        
        print(cleaned_title, file_name,video_url)
        file_path=self.convert_to_mp3(video_url)
        cover_path = self.extract_cover(video_url)
        cover_url = save_cover_to_static(cover_path)

        print('file——path',file_path)
        return AudioDownloadResult(
            file_path=file_path,
            title=cleaned_title,  # 使用清理后的标题
            duration=0,  # 可选：后续加上读取时长
            cover_url=cover_url,  # 暂无封面
            platform="local",
            video_id=cleaned_title,  # 使用清理后的标题作为video_id
            raw_info={
                'path':  file_path
            },
            video_path=None
        )
