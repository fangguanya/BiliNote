from typing import List
from app.gpt.base import GPT
from openai import OpenAI
from app.gpt.prompt import BASE_PROMPT, AI_SUM, SCREENSHOT
from app.gpt.provider.OpenAI_compatible_provider import OpenAICompatibleProvider
from app.gpt.utils import fix_markdown, estimate_tokens, estimate_mixed_content_tokens, split_segments_by_tokens, merge_markdown_contents, create_chunk_summary_prompt
from app.models.gpt_model import GPTSource
from app.models.transcriber_model import TranscriptSegment
from app.utils.retry_utils import retry_on_rate_limit
from datetime import timedelta
from app.utils.logger import get_logger

logger = get_logger(__name__)


class QwenGPT(GPT):
    def __init__(self):
        from os import getenv
        self.api_key = getenv("QWEN_API_KEY")
        self.base_url = getenv("QWEN_API_BASE_URL")
        self.model=getenv('QWEN_MODEL')
        print(self.model)
        self.client = OpenAICompatibleProvider(api_key=self.api_key, base_url=self.base_url)
        self.screenshot = False

    def _format_time(self, seconds: float) -> str:
        return str(timedelta(seconds=int(seconds)))[2:]  # e.g., 03:15

    def _build_segment_text(self, segments: List[TranscriptSegment]) -> str:
        return "\n".join(
            f"{self._format_time(seg.start)} - {seg.text.strip()}"
            for seg in segments
        )

    def ensure_segments_type(self, segments) -> List[TranscriptSegment]:
        return [
            TranscriptSegment(**seg) if isinstance(seg, dict) else seg
            for seg in segments
        ]

    def create_messages(self, segments: List[TranscriptSegment], title: str, tags: str, chunk_prompt: str = ""):
        content = BASE_PROMPT.format(
            video_title=title,
            segment_text=self._build_segment_text(segments),
            tags=tags
        )
        
        # 添加分块处理的特殊prompt（如果有的话）
        if chunk_prompt:
            content = chunk_prompt + "\n\n" + content
            
        if self.screenshot:
            print(":需要截图")
            content += SCREENSHOT
        print(content)
        return [{"role": "user", "content": content + AI_SUM}]
        
    def list_models(self):
        return self.client.list_models()
        
    @retry_on_rate_limit(max_retries=3, delay=30.0, backoff_factor=1.5)
    def _summarize_chunk(self, segments: List[TranscriptSegment], title: str, tags: str, chunk_prompt: str = "") -> str:
        """处理单个分块的总结"""
        messages = self.create_messages(segments, title, tags, chunk_prompt)
        
        # 估算当前prompt的token数
        prompt_text = str(messages)
        prompt_tokens = estimate_tokens(prompt_text)
        logger.info(f"📊 当前分块prompt token估算: {prompt_tokens}")
        
        response = self.client.chat(
            model=self.model,
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
        
    @retry_on_rate_limit(max_retries=3, delay=30.0, backoff_factor=1.5)
    def summarize(self, source: GPTSource) -> str:
        self.screenshot = source.screenshot
        source.segment = self.ensure_segments_type(source.segment)
        
        # 首先估算总token数
        full_segment_text = self._build_segment_text(source.segment)
        
        # 创建完整的prompt文本（不包含图片）
        full_content_text = self._create_prompt_text(
            title=source.title,
            segment_text=full_segment_text,
            tags=source.tags,
            link=source.link,
            screenshot=source.screenshot
        )
        
        # 估算总token数（包含文本和图片）
        video_img_urls = source.video_img_urls or []
        estimated_tokens = estimate_mixed_content_tokens(full_content_text, video_img_urls)
        
        logger.info(f"📊 混合内容token估算: {estimated_tokens}")
        logger.info(f"📊 其中转录文本: {estimate_tokens(full_segment_text)}")
        logger.info(f"📊 其中图片内容: {len(video_img_urls)}张图片")
        
        # 设置token限制（根据不同模型调整）
        max_tokens = 80000  # 默认限制
        if 'qwen' in self.model.lower():
            # Qwen模型的实际限制根据具体版本调整
            if 'qwen2.5-vl-72b' in self.model.lower():
                max_tokens = 80000   # 实际测试发现96000是最大长度，但预留更多空间
            # elif 'qwen2.5' in self.model.lower():
            #     max_tokens = 120000  # 其他qwen2.5版本
            else:
                max_tokens = 80000   # 保守设置
        
        logger.info(f"📊 模型 {self.model} 的token限制: {max_tokens}")
        
        # 如果内容在限制范围内，直接处理
        if estimated_tokens <= max_tokens - 10000:  # 增加预留token空间到10000
            logger.info("📝 内容未超出限制，直接处理")
            messages = self.create_messages(source.segment, source.title, source.tags)
            response = self.client.chat(
                model=self.model,
                messages=messages,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        
        # 内容过长，需要分块处理
        logger.warning(f"⚠️ 内容过长 ({estimated_tokens} tokens)，启用分块处理模式")
        
        # 分割segments
        segment_chunks = split_segments_by_tokens(source.segment, max_tokens)
        logger.info(f"🔄 已分割为 {len(segment_chunks)} 个分块")
        
        # 处理每个分块
        chunk_results = []
        for i, chunk_segments in enumerate(segment_chunks):
            chunk_index = i + 1
            is_first = (i == 0)
            is_last = (i == len(segment_chunks) - 1)
            
            logger.info(f"🔄 处理分块 {chunk_index}/{len(segment_chunks)}: {len(chunk_segments)} 个片段")
            
            # 为当前分块创建特殊的prompt
            chunk_prompt = create_chunk_summary_prompt(
                chunk_index=chunk_index,
                total_chunks=len(segment_chunks),
                is_first=is_first,
                is_last=is_last
            )
            
            try:
                chunk_result = self._summarize_chunk(
                    chunk_segments,
                    source.title,
                    source.tags,
                    chunk_prompt
                )
                
                chunk_results.append(chunk_result)
                logger.info(f"✅ 分块 {chunk_index}/{len(segment_chunks)} 处理完成")
                
            except Exception as e:
                logger.error(f"❌ 分块 {chunk_index} 处理失败: {e}")
                # 如果某个分块失败，添加错误信息
                chunk_results.append(f"## 第 {chunk_index} 部分\n\n*此部分处理失败: {str(e)}*\n")
        
        # 合并所有分块结果
        logger.info(f"🔗 开始合并 {len(chunk_results)} 个分块结果")
        final_result = merge_markdown_contents(chunk_results)
        
        logger.info(f"✅ 分块处理和合并完成，最终内容长度: {len(final_result)} 字符")
        return final_result

if __name__ == '__main__':
    gpt = QwenGPT()
    print(gpt.list_models())
