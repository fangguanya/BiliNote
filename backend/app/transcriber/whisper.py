"""
PyTorch Whisper 转写器
使用 openai-whisper 库，原生支持 CUDA 13
"""
import os
import torch
import whisper
import threading

from app.decorators.timeit import timeit
from app.models.transcriber_model import TranscriptSegment, TranscriptResult
from app.transcriber.base import Transcriber
from app.utils.logger import get_logger
from app.utils.path_helper import get_model_dir
from events import transcription_finished


logger = get_logger(__name__)

# 🔒 全局锁：保护GPU模型不被多线程同时访问
_whisper_lock = threading.Lock()


class WhisperTranscriber(Transcriber):
    """
    基于 OpenAI Whisper (PyTorch) 的转写器
    
    特性：
    - 原生支持 CUDA 13
    - 基于 PyTorch，稳定可靠
    - 支持 FP16 加速
    """
    
    def __init__(
        self,
        model_size: str = "base",
        device: str = "cuda",
        language: str = "zh",
        fp16: bool = True,
    ):
        """
        初始化 Whisper 转写器
        
        Args:
            model_size: 模型大小 (tiny/base/small/medium/large/large-v2/large-v3)
            device: 设备 (cuda/cpu)
            language: 语言代码 (zh/en/auto)
            fp16: 是否使用 FP16 加速（仅CUDA可用）
        """
        self.model_size = model_size
        self.language = None if language == "auto" else language
        self.fp16 = fp16 if device == "cuda" else False
        
        # 🔧 设备检测与验证
        if device == "cuda":
            if not self._check_cuda():
                error_msg = (
                    "❌ CUDA不可用但被要求使用GPU模式！\n"
                    "请检查：\n"
                    "1. 运行 nvidia-smi 确认GPU可用\n"
                    "2. 确认PyTorch支持CUDA: python -c \"import torch; print(torch.cuda.is_available())\"\n"
                    "3. 如需使用CPU模式，请在配置中将device改为'cpu'"
                )
                logger.error(error_msg)
                raise RuntimeError("CUDA不可用，无法启动GPU模式")
            
            self.device = "cuda"
            logger.info("✅ CUDA检测通过，强制使用GPU模式")
            logger.info(f"   GPU设备: {torch.cuda.get_device_name(0)}")
            logger.info(f"   CUDA版本: {torch.version.cuda}")
            logger.info(f"   PyTorch版本: {torch.__version__}")
            logger.info(f"   FP16加速: {'启用' if self.fp16 else '禁用'}")
        else:
            self.device = "cpu"
            self.fp16 = False
            logger.info("💻 使用CPU模式（不推荐，速度较慢）")
        
        # 🔧 加载模型
        self._load_model()
    
    def _check_cuda(self) -> bool:
        """检查 CUDA 是否可用"""
        try:
            import torch
            if not torch.cuda.is_available():
                logger.error("❌ PyTorch检测不到CUDA")
                return False
            
            # 测试 CUDA 是否真的可用
            try:
                _ = torch.zeros(1).cuda()
                logger.info("✅ CUDA功能测试通过")
                return True
            except Exception as e:
                logger.error(f"❌ CUDA功能测试失败: {e}")
                return False
                
        except ImportError:
            logger.error("❌ PyTorch未安装")
            return False
    
    def _load_model(self):
        """加载 Whisper 模型"""
        try:
            logger.info(f"🚀 开始加载 Whisper 模型...")
            logger.info(f"   模型大小: {self.model_size}")
            logger.info(f"   设备: {self.device}")
            logger.info(f"   语言: {self.language or '自动检测'}")
            
            # 🔧 设置模型下载目录
            model_dir = get_model_dir("whisper")
            os.makedirs(model_dir, exist_ok=True)
            
            # 🔧 加载模型（使用模型名称，不是路径）
            # openai-whisper 会自动下载到 download_root 目录
            logger.info(f"🔧 正在加载模型到 {self.device}...")
            logger.info(f"   模型将下载到: {model_dir}")
            
            self.model = whisper.load_model(
                name=self.model_size,  # 使用模型名称，不是路径
                device=self.device,
                download_root=model_dir,
            )
            
            logger.info(f"✅ Whisper 模型加载成功！")
            logger.info(f"   模型参数量: ~{self._get_model_params()}M")
            
        except Exception as e:
            import traceback
            logger.error(f"❌ Whisper 模型加载失败！")
            logger.error(f"   错误类型: {type(e).__name__}")
            logger.error(f"   错误信息: {str(e)}")
            logger.error(f"   完整堆栈:")
            for line in traceback.format_exc().splitlines():
                logger.error(f"   {line}")
            raise
    
    def _get_model_params(self) -> int:
        """获取模型参数量（百万）"""
        params_map = {
            "tiny": 39,
            "base": 74,
            "small": 244,
            "medium": 769,
            "large": 1550,
            "large-v1": 1550,
            "large-v2": 1550,
            "large-v3": 1550,
        }
        return params_map.get(self.model_size, 0)
    
    @timeit
    def transcript(self, file_path: str) -> TranscriptResult:
        """
        转写音频文件
        
        Args:
            file_path: 音频文件路径
            
        Returns:
            TranscriptResult: 转写结果
        """
        try:
            logger.info(f"🎤 开始转写音频...")
            logger.info(f"   音频路径: {file_path}")
            logger.info(f"   模型: {self.model_size}")
            logger.info(f"   设备: {self.device}")
            
            # 🔧 再次检查 CUDA 状态
            if self.device == "cuda":
                if not torch.cuda.is_available():
                    raise RuntimeError("转写时CUDA不可用！")
                logger.info(f"   GPU显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB")
            
            # 🔒 获取全局锁，防止多线程同时使用GPU模型
            logger.info(f"🔒 等待获取GPU锁...")
            with _whisper_lock:
                logger.info(f"✅ 已获取GPU锁，开始执行转写...")
                
                # 🔧 执行转写
                result = self.model.transcribe(
                    audio=file_path,
                    language=self.language,
                    fp16=self.fp16,
                    verbose=False,  # 不打印进度
                    task="transcribe",  # 转写任务（不是翻译）
                )
                
                logger.info(f"🔓 转写完成，释放GPU锁")
            
            logger.info(f"✅ 转写完成，开始处理结果...")
            
            # 🔧 解析结果
            segments = []
            full_text = ""
            
            for seg in result["segments"]:
                text = seg["text"].strip()
                full_text += text + " "
                segments.append(TranscriptSegment(
                    start=seg["start"],
                    end=seg["end"],
                    text=text
                ))
            
            detected_language = result.get("language", "unknown")
            logger.info(f"✅ 检测到语言: {detected_language}")
            logger.info(f"✅ 转写片段数: {len(segments)}")
            logger.info(f"✅ 文本长度: {len(full_text)} 字符")
            
            transcript_result = TranscriptResult(
                language=detected_language,
                full_text=full_text.strip(),
                segments=segments,
                raw=result  # 保存原始结果
            )
            
            return transcript_result
            
        except Exception as e:
            import traceback
            logger.error(f"❌ 转写失败！")
            logger.error(f"   错误类型: {type(e).__name__}")
            logger.error(f"   错误信息: {str(e)}")
            logger.error(f"   音频路径: {file_path}")
            logger.error(f"   模型: {self.model_size}")
            logger.error(f"   设备: {self.device}")
            logger.error(f"   完整堆栈:")
            for line in traceback.format_exc().splitlines():
                logger.error(f"   {line}")
            raise  # 直接抛出异常，不做降级处理
    
    def on_finish(self, video_path: str, result: TranscriptResult) -> None:
        """转写完成回调"""
        logger.info("✅ 转写完成，发送事件通知")
        transcription_finished.send({
            "file_path": video_path,
        })
    
    @staticmethod
    def is_cuda() -> bool:
        """检查 CUDA 是否可用（静态方法，用于兼容）"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    @staticmethod
    def is_torch_installed() -> bool:
        """检查 PyTorch 是否已安装（静态方法，用于兼容）"""
        try:
            import torch
            return True
        except ImportError:
            return False
