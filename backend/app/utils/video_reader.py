import base64
import os
import re
import subprocess
import ffmpeg
from PIL import Image, ImageDraw, ImageFont
import logging
from pathlib import Path
import cv2
import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)

class VideoReader:
    """
    一个视频读取器，使用OpenCV从视频文件中高效地提取帧。
    这个类被设计为上下文管理器,以确保视频资源被正确打开和释放。

    使用示例:
    with VideoReader("/path/to/video.mp4") as reader:
        frame_path = reader.get_frame_image(ts=10.5, output_path="/path/to/save/frame.jpg", scale=0.5)
        if frame_path:
            print(f"帧已保存到: {frame_path}")
    """
    def __init__(self, video_path: str):
        """
        初始化VideoReader。

        Args:
            video_path (str): 视频文件的路径。
        """
        if not Path(video_path).exists():
            raise FileNotFoundError(f"视频文件未找到: {video_path}")
        self.video_path = video_path
        self.cap = None

    def __enter__(self):
        """作为上下文管理器的一部分，打开视频文件。"""
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            # 使用logging记录错误，而不是IOError，以便更灵活地处理
            logger.error(f"无法打开视频文件: {self.video_path}")
            # 返回self以便调用者可以检查状态，尽管后续操作会失败
            return self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """作为上下文管理器的一部分，在退出时释放视频捕获对象。"""
        if self.cap:
            self.cap.release()
            logger.debug(f"视频文件已释放: {self.video_path}")

    def get_frame(self, ts: float, scale: float = None) -> np.ndarray | None:
        """
        在指定时间戳 (秒) 提取一帧，并以numpy数组形式返回。

        Args:
            ts (float): 目标帧的时间戳 (以秒为单位)。
            scale (float, optional): 缩放因子 (0.0到1.0之间)。

        Returns:
            np.ndarray | None: 如果成功，则返回帧的numpy数组，否则返回None。
        """
        if not self.cap or not self.cap.isOpened():
            logger.error("VideoReader 未初始化或视频文件无法打开。")
            return None

        self.cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
        success, frame = self.cap.read()

        if not success:
            logger.warning(f"无法在时间戳 {ts:.2f}s 从视频 {self.video_path} 读取帧。")
            return None

        if scale and 0 < scale < 1:
            frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        
        return frame

    def get_frame_image(self, ts: float, output_path: str, scale: float = None) -> str | None:
        """
        在指定时间戳 (秒) 提取一帧，并将其保存为图像文件。

        Args:
            ts (float): 目标帧的时间戳 (以秒为单位)。
            output_path (str): 保存输出图像的路径。
            scale (float, optional): 缩放因子 (0.0到1.0之间)。例如 0.5 表示将分辨率降低到50%。
                                     默认为None (不缩放)。

        Returns:
            str | None: 如果成功，则返回输出文件的路径，否则返回None。
        """
        frame = self.get_frame(ts, scale)
        if frame is None:
            return None

        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # 保存帧为图像文件
            if not cv2.imwrite(output_path, frame):
                raise IOError(f"无法将帧写入到文件: {output_path}")
            
            logger.debug(f"成功提取并保存帧到 {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"在处理或保存帧时发生错误 (ts={ts:.2f}s, path={output_path}): {e}", exc_info=True)
            return None


