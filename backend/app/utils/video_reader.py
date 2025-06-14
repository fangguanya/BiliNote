import base64
import os
import re
import subprocess
import ffmpeg
from PIL import Image, ImageDraw, ImageFont

from app.utils.logger import get_logger
from app.utils.path_helper import get_app_dir

logger = get_logger(__name__)
class VideoReader:
    def __init__(self,
                 video_path: str,
                 grid_size=(3, 3),
                 frame_interval=2,
                 unit_width=960,
                 unit_height=540,
                 save_quality=90,
                 font_path="fonts/arial.ttf",
                 frame_dir=None,
                 grid_dir=None):
        self.video_path = video_path
        self.grid_size = grid_size
        self.frame_interval = frame_interval
        self.unit_width = unit_width
        self.unit_height = unit_height
        self.save_quality = save_quality
        self.frame_dir = frame_dir or get_app_dir("output_frames")
        self.grid_dir = grid_dir or get_app_dir("grid_output")
        print(f"视频路径：{video_path}",self.frame_dir,self.grid_dir)
        self.font_path = font_path

    def format_time(self, seconds: float) -> str:
        mm = int(seconds // 60)
        ss = int(seconds % 60)
        return f"{mm:02d}_{ss:02d}"

    def extract_time_from_filename(self, filename: str) -> float:
        match = re.search(r"frame_(\d{2})_(\d{2})\.jpg", filename)
        if match:
            mm, ss = map(int, match.groups())
            return mm * 60 + ss
        return float('inf')

    def extract_frames(self, max_frames=1000) -> list[str]:
        """
        从视频中提取帧，支持多种ffmpeg参数组合和错误处理
        """
        try:
            os.makedirs(self.frame_dir, exist_ok=True)
            duration = float(ffmpeg.probe(self.video_path)["format"]["duration"])
            timestamps = [i for i in range(0, int(duration), self.frame_interval)][:max_frames]

            image_paths = []
            for ts in timestamps:
                time_label = self.format_time(ts)
                output_path = os.path.join(self.frame_dir, f"frame_{time_label}.jpg")
                
                # 尝试不同的ffmpeg命令组合
                commands = [
                    # 方案1: 使用严格模式和像素格式
                    ["ffmpeg", "-strict", "-2", "-i", self.video_path, "-ss", str(ts), 
                     "-frames:v", "1", "-q:v", "2", "-pix_fmt", "yuvj420p", 
                     "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", 
                     "-y", output_path, "-hide_banner", "-loglevel", "error"],
                    
                    # 方案2: 使用原始命令
                    ["ffmpeg", "-i", self.video_path, "-ss", str(ts), 
                     "-frames:v", "1", "-q:v", "2", "-y", output_path, 
                     "-hide_banner", "-loglevel", "error"],
                    
                    # 方案3: 使用不同的像素格式
                    ["ffmpeg", "-i", self.video_path, "-ss", str(ts), 
                     "-frames:v", "1", "-q:v", "2", "-pix_fmt", "rgb24", 
                     "-y", output_path, "-hide_banner", "-loglevel", "error"],
                    
                    # 方案4: 简化命令
                    ["ffmpeg", "-i", self.video_path, "-ss", str(ts), 
                     "-frames:v", "1", "-y", output_path]
                ]
                
                success = False
                for i, cmd in enumerate(commands):
                    try:
                        logger.info(f"尝试方案{i+1}提取帧 {time_label}")
                        subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
                        image_paths.append(output_path)
                        success = True
                        break
                    except subprocess.CalledProcessError as e:
                        logger.warning(f"方案{i+1}失败: {e}")
                        continue
                
                if not success:
                    logger.error(f"无法提取时间点 {time_label} 的帧，尝试了所有方案")
                    
            return image_paths
        except Exception as e:
            logger.error(f"分割帧发生错误：{str(e)}")
            raise ValueError("视频处理失败")

    def group_images(self) -> list[list[str]]:
        image_files = [os.path.join(self.frame_dir, f) for f in os.listdir(self.frame_dir) if
                       f.startswith("frame_") and f.endswith(".jpg")]
        image_files.sort(key=lambda f: self.extract_time_from_filename(os.path.basename(f)))
        group_size = self.grid_size[0] * self.grid_size[1]
        return [image_files[i:i + group_size] for i in range(0, len(image_files), group_size)]

    def concat_images(self, image_paths: list[str], name: str) -> str:
        os.makedirs(self.grid_dir, exist_ok=True)
        font = ImageFont.truetype(self.font_path, 48) if os.path.exists(self.font_path) else ImageFont.load_default()
        images = []

        for path in image_paths:
            img = Image.open(path).convert("RGB").resize((self.unit_width, self.unit_height), Image.Resampling.LANCZOS)
            timestamp = re.search(r"frame_(\d{2})_(\d{2})\.jpg", os.path.basename(path))
            time_text = f"{timestamp.group(1)}:{timestamp.group(2)}" if timestamp else ""
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), time_text, fill="yellow", font=font, stroke_width=1, stroke_fill="black")
            images.append(img)

        cols, rows = self.grid_size
        grid_img = Image.new("RGB", (self.unit_width * cols, self.unit_height * rows), (255, 255, 255))

        for i, img in enumerate(images):
            x = (i % cols) * self.unit_width
            y = (i // cols) * self.unit_height
            grid_img.paste(img, (x, y))

        save_path = os.path.join(self.grid_dir, f"{name}.jpg")
        grid_img.save(save_path, quality=self.save_quality)
        return save_path

    def encode_images_to_base64(self, image_paths: list[str]) -> list[str]:
        base64_images = []
        max_size_mb = 1  # 设置单个图片最大
        
        for path in image_paths:
            try:
                # 先检查原始文件大小
                file_size_mb = os.path.getsize(path) / (1024 * 1024)
                
                # 如果文件太大，需要压缩
                if file_size_mb > max_size_mb:
                    logger.warning(f"⚠️ 图片过大({file_size_mb:.2f}MB)，开始压缩...")
                    
                    # 重新保存以压缩图片
                    img = Image.open(path)
                    
                    # 计算需要的压缩质量
                    target_quality = max(20, int(85 * (max_size_mb / file_size_mb)))
                    
                    # 如果还是太大，可能需要缩小尺寸
                    if target_quality < 30:
                        scale_factor = 0.8
                        new_width = int(img.width * scale_factor)
                        new_height = int(img.height * scale_factor)
                        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        target_quality = 50
                    
                    # 保存压缩后的图片到临时路径
                    temp_path = path.replace('.jpg', '_compressed.jpg')
                    img.save(temp_path, quality=target_quality, optimize=True)
                    
                    # 检查压缩后的大小
                    compressed_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
                    
                    # 使用压缩后的图片
                    use_path = temp_path
                else:
                    use_path = path
                
                # 编码为base64
                with open(use_path, "rb") as img_file:
                    encoded_string = base64.b64encode(img_file.read()).decode("utf-8")
                    
                    # 检查base64编码后的大小
                    base64_size_mb = len(encoded_string) * 3 / 4 / (1024 * 1024)  # base64编码约增加33%
                    
                    if base64_size_mb > max_size_mb:
                        logger.error(f"❌ base64编码后仍然过大: {base64_size_mb:.2f}MB，跳过此图片")
                        continue
                    
                    base64_images.append(f"data:image/jpeg;base64,{encoded_string}")
                
                # 清理临时文件
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.remove(temp_path)
                    
            except Exception as e:
                logger.error(f"❌ 处理图片失败 {path}: {e}")
                continue
        
        # 检查总大小
        total_size_mb = sum(len(img.split(',')[1]) * 3 / 4 for img in base64_images) / (1024 * 1024)
        logger.warning(f"📊 总图片大小: {total_size_mb:.2f}MB, 图片数量: {len(base64_images)}")
        
        if total_size_mb > 4.5:  # 留一些余量
            logger.warning(f"⚠️ 总图片大小过大({total_size_mb:.2f}MB)，只保留前几张图片")
            # 只保留能确保在限制范围内的图片
            filtered_images = []
            current_size = 0
            for img in base64_images:
                img_size = len(img.split(',')[1]) * 3 / 4 / (1024 * 1024)
                if current_size + img_size <= 4.0:  # 保守限制在4MB
                    filtered_images.append(img)
                    current_size += img_size
                else:
                    break
            base64_images = filtered_images
            logger.warning(f"✅ 过滤后保留 {len(base64_images)} 张图片，总大小: {current_size:.2f}MB")
        
        return base64_images

    def run(self)->list[str]:
        # logger.info("🚀 开始提取视频帧...")  # 删除冗余日志
        try:
            # 确保目录存在
            print(self.frame_dir,self.grid_dir)
            os.makedirs(self.frame_dir, exist_ok=True)
            os.makedirs(self.grid_dir, exist_ok=True)
            #清空帧文件夹
            for file in os.listdir(self.frame_dir):
                if file.startswith("frame_"):
                    os.remove(os.path.join(self.frame_dir, file))
            print(self.frame_dir,self.grid_dir)
            #清空网格文件夹
            for file in os.listdir(self.grid_dir):
                if file.startswith("grid_"):
                    os.remove(os.path.join(self.grid_dir, file))
            print(self.frame_dir,self.grid_dir)
            self.extract_frames()
            print("2#3",self.frame_dir,self.grid_dir)
            # logger.info("🧩 开始拼接网格图...")  # 删除冗余日志
            image_paths = []
            groups = self.group_images()
            for idx, group in enumerate(groups, start=1):
                if len(group) < self.grid_size[0] * self.grid_size[1]:
                    logger.warning(f"⚠️ 跳过第 {idx} 组，图片不足 {self.grid_size[0] * self.grid_size[1]} 张")
                    continue
                out_path = self.concat_images(group, f"grid_{idx}")
                image_paths.append(out_path)

            # logger.info("📤 开始编码图像...")  # 删除冗余日志
            urls = self.encode_images_to_base64(image_paths)
            return urls
        except Exception as e:
            logger.error(f"发生错误：{str(e)}")
            raise ValueError("视频处理失败")


