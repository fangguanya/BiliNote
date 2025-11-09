from app.gpt.base import GPT
from app.gpt.prompt_builder import generate_base_prompt
from app.models.gpt_model import GPTSource
from app.gpt.prompt import BASE_PROMPT, AI_SUM, SCREENSHOT, LINK
from app.gpt.utils import fix_markdown, estimate_tokens, estimate_mixed_content_tokens, split_segments_by_tokens, split_segments_with_images_by_tokens, merge_markdown_contents, create_chunk_summary_prompt
from app.models.transcriber_model import TranscriptSegment
from app.utils.retry_utils import retry_on_rate_limit
from datetime import timedelta
from typing import List
from app.utils.logger import get_logger

logger = get_logger(__name__)


class UniversalGPT(GPT):
    def __init__(self, client, model: str, temperature: float = 0.7):
        self.client = client
        self.model = model
        self.temperature = temperature
        self.screenshot = False
        self.screenshot = False
        self.link = False

    def _format_time(self, seconds: float) -> str:
        return str(timedelta(seconds=int(seconds)))[2:]

    def _build_segment_text(self, segments: List[TranscriptSegment]) -> str:
        """构建转录文本，如果没有转录则返回空字符串"""
        if not segments:
            return ""
        return "\n".join(
            f"{self._format_time(seg.start)} - {seg.text.strip()}"
            for seg in segments
        )

    def ensure_segments_type(self, segments) -> List[TranscriptSegment]:
        return [TranscriptSegment(**seg) if isinstance(seg, dict) else seg for seg in segments]

    def create_messages(self, segments: List[TranscriptSegment], **kwargs):

        content_text = generate_base_prompt(
            title=kwargs.get('title'),
            segment_text=self._build_segment_text(segments),
            tags=kwargs.get('tags'),
            _format=kwargs.get('_format'),
            style=kwargs.get('style'),
            extras=kwargs.get('extras'),
        )
        
        # 添加分块处理的特殊prompt（如果有的话）
        chunk_prompt = kwargs.get('chunk_prompt', '')
        if chunk_prompt:
            content_text = chunk_prompt + "\n\n" + content_text

        # ⛳ 组装 content 数组，支持 text + image_url 混合
        content = [{"type": "text", "text": content_text}]
        video_img_urls = kwargs.get('video_img_urls', [])

        for url in video_img_urls:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": url,
                    "detail": "auto"
                }
            })

        # ✅ 正确格式：整体包在一个 message 里，role + content array
        messages = [{
            "role": "user",
            "content": content
        }]

        return messages

    def list_models(self):
        return self.client.models.list()

    @retry_on_rate_limit(max_retries=3, delay=30.0, backoff_factor=1.5)
    def _summarize_chunk(self, segments: List[TranscriptSegment], **kwargs) -> str:
        """处理单个分块的总结"""
        messages = self.create_messages(segments, **kwargs)
        
        # 估算当前prompt的token数
        prompt_text = str(messages)
        prompt_tokens = estimate_tokens(prompt_text)
        logger.info(f"📊 当前分块prompt token估算: {prompt_tokens}")
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()

    @retry_on_rate_limit(max_retries=3, delay=30.0, backoff_factor=1.5)
    def summarize(self, source: GPTSource) -> str:
        self.screenshot = source.screenshot
        self.link = source.link
        source.segment = self.ensure_segments_type(source.segment)

        # 构建基础转录文本
        full_segment_text = self._build_segment_text(source.segment)
        
        # 创建完整的prompt文本（不包含图片）
        full_content_text = generate_base_prompt(
            title=source.title,
            segment_text=full_segment_text,
            tags=source.tags,
            _format=source._format,
            style=source.style,
            extras=source.extras,
        )
        
        # 估算总token数（包含文本和图片）
        video_img_urls = source.video_img_urls or []
        estimated_tokens = estimate_mixed_content_tokens(full_content_text, video_img_urls)
        
        logger.info(f"📊 混合内容token估算: {estimated_tokens}")
        logger.info(f"📊 其中转录文本: {estimate_tokens(full_segment_text)}")
        logger.info(f"📊 其中图片内容: {len(video_img_urls)}张图片")
        
        # 设置token限制（根据不同模型调整）
        max_tokens = 80000
        if 'gpt-4' in self.model.lower():
            max_tokens = 120000  # GPT-4有更高的限制
        elif 'gpt-3.5' in self.model.lower():
            max_tokens = 14000   # GPT-3.5限制更低
        elif 'claude' in self.model.lower():
            max_tokens = 180000  # Claude有很高的限制
        elif 'qwen' in self.model.lower():
            # Qwen模型的实际限制根据具体版本调整
            if 'qwen2.5-vl-72b' in self.model.lower():
                max_tokens = 80000   # 实际测试发现96000是最大长度，但预留更多空间
            # elif 'qwen2.5' in self.model.lower():
            #     max_tokens = 120000  # 其他qwen2.5版本
            else:
                max_tokens = 80000   # 保守设置
        elif 'deepseek' in self.model.lower():
            max_tokens = 120000  # DeepSeek限制
        elif 'yi-' in self.model.lower() or 'yi_' in self.model.lower():
            max_tokens = 120000  # Yi系列模型
        
        logger.info(f"📊 模型 {self.model} 的token限制: {max_tokens}")
        
        # 如果内容在限制范围内，直接处理
        if estimated_tokens <= max_tokens - 10000:  # 增加预留token空间到10000
            logger.info("📝 内容未超出限制，直接处理")
            messages = self.create_messages(
                source.segment,
                title=source.title,
                tags=source.tags,
                video_img_urls=source.video_img_urls,
                _format=source._format,
                style=source.style,
                extras=source.extras
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        
        # 内容过长，需要分块处理
        logger.warning(f"⚠️ 内容过长 ({estimated_tokens} tokens)，启用分块处理模式")
        
        # 使用新的混合内容分割函数
        chunk_results = split_segments_with_images_by_tokens(
            source.segment, 
            video_img_urls, 
            max_tokens
        )
        logger.info(f"🔄 已分割为 {len(chunk_results)} 个分块")
        
        # 处理每个分块
        summary_results = []
        for i, (chunk_segments, chunk_images) in enumerate(chunk_results):
            chunk_index = i + 1
            is_first = (i == 0)
            is_last = (i == len(chunk_results) - 1)
            
            logger.info(f"🔄 处理分块 {chunk_index}/{len(chunk_results)}: {len(chunk_segments)}个片段, {len(chunk_images)}张图片")
            
            # 为当前分块创建特殊的prompt
            chunk_prompt = create_chunk_summary_prompt(
                chunk_index=chunk_index,
                total_chunks=len(chunk_results),
                is_first=is_first,
                is_last=is_last
            )
            
            try:
                chunk_result = self._summarize_chunk(
                    chunk_segments,
                    title=source.title,
                    tags=source.tags,
                    video_img_urls=chunk_images,  # 只传递分配给当前分块的图片
                    _format=source._format,
                    style=source.style,
                    extras=source.extras,
                    chunk_prompt=chunk_prompt
                )
                
                summary_results.append(chunk_result)
                logger.info(f"✅ 分块 {chunk_index}/{len(chunk_results)} 处理完成")
                
            except Exception as e:
                logger.error(f"❌ 分块 {chunk_index} 处理失败: {e}")
                # 如果某个分块失败，添加错误信息
                summary_results.append(f"## 第 {chunk_index} 部分\n\n*此部分处理失败: {str(e)}*\n")
        
        # 合并所有分块结果
        logger.info(f"🔗 开始合并 {len(summary_results)} 个分块结果")
        final_result = merge_markdown_contents(summary_results)
        
        logger.info(f"✅ 分块处理和合并完成，最终内容长度: {len(final_result)} 字符")
        return final_result
