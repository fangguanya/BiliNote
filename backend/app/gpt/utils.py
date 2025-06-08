import re
import math
from typing import List, Tuple
from app.models.transcriber_model import TranscriptSegment
from app.utils.logger import get_logger

logger = get_logger(__name__)

def fix_markdown(content: str) -> str:
    """修复markdown格式的函数（原有功能保持）"""
    if not content:
        return content
    
    # 修复可能的格式问题
    content = re.sub(r'^```markdown\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n```\s*$', '', content, flags=re.MULTILINE)
    
    return content.strip()


def estimate_tokens(text: str) -> int:
    """
    更准确地估算文本的token数量
    基于实际测试调整的估算公式，更接近真实token数量
    """
    if not text:
        return 0
    
    # 计算总字符数
    total_chars = len(text)
    
    # 计算中文字符数量
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    
    # 计算英文单词数量  
    english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
    
    # 计算数字、符号、标点等
    other_chars = total_chars - chinese_chars - sum(len(word) for word in re.findall(r'\b[a-zA-Z]+\b', text))
    
    # 更保守的估算：
    # - 中文字符按2个token计算（之前1.5偏小）
    # - 英文单词按1.3个token计算（考虑子词分割）
    # - 其他字符按0.8个token计算
    # - 再加20%的安全余量
    estimated_tokens = int((chinese_chars * 2.0 + english_words * 1.3 + other_chars * 0.8) * 1.2)
    
    logger.info(f"📊 Token估算详情: 总字符={total_chars}, 中文={chinese_chars}, 英文单词={english_words}, 其他={other_chars}, 估算tokens={estimated_tokens}")
    
    return estimated_tokens


def split_segments_by_tokens(segments: List[TranscriptSegment], max_tokens: int = 80000) -> List[List[TranscriptSegment]]:
    """
    根据token限制将转录片段分割成多个组
    
    Args:
        segments: 转录片段列表
        max_tokens: 每组的最大token数
    
    Returns:
        分割后的片段组列表
    """
    if not segments:
        return []
    
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    # 为prompt模板预留token空间
    template_reserve = 10000  # 增加预留空间，为prompt模板、标题、标签等预留更多token
    actual_max_tokens = max_tokens - template_reserve
    
    logger.info(f"📊 开始分割转录片段，最大token数: {actual_max_tokens} (预留: {template_reserve})")
    
    for i, segment in enumerate(segments):
        segment_text = f"{format_time_from_seconds(segment.start)} - {segment.text.strip()}"
        segment_tokens = estimate_tokens(segment_text)
        
        # 如果当前片段加入后会超出限制，且当前组不为空，则开始新组
        if current_tokens + segment_tokens > actual_max_tokens and current_chunk:
            logger.info(f"📦 完成分块 {len(chunks) + 1}: {len(current_chunk)} 个片段, {current_tokens} tokens")
            chunks.append(current_chunk)
            current_chunk = [segment]
            current_tokens = segment_tokens
        else:
            current_chunk.append(segment)
            current_tokens += segment_tokens
    
    # 添加最后一个组
    if current_chunk:
        logger.info(f"📦 完成分块 {len(chunks) + 1}: {len(current_chunk)} 个片段, {current_tokens} tokens")
        chunks.append(current_chunk)
    
    logger.info(f"✅ 分割完成，共生成 {len(chunks)} 个分块")
    return chunks


def format_time_from_seconds(seconds: float) -> str:
    """将秒数格式化为时间字符串 HH:MM:SS"""
    from datetime import timedelta
    return str(timedelta(seconds=int(seconds)))[2:]  # 去掉小时前缀的0:


def merge_markdown_contents(contents: List[str]) -> str:
    """
    合并多个markdown内容，智能处理重复的标题和内容
    
    Args:
        contents: markdown内容列表
    
    Returns:
        合并后的markdown内容
    """
    if not contents:
        return ""
    
    if len(contents) == 1:
        return contents[0]
    
    logger.info(f"🔗 开始合并 {len(contents)} 个markdown内容")
    
    merged_content = []
    section_counter = 1
    
    # 提取第一个内容的标题部分（通常包含视频标题等信息）
    first_content = contents[0].strip()
    
    # 查找第一个二级标题的位置，之前的内容作为头部
    header_match = re.search(r'\n## ', first_content)
    if header_match:
        header = first_content[:header_match.start()].strip()
        merged_content.append(header)
        merged_content.append("\n")
    
    # 处理每个分块的内容
    for i, content in enumerate(contents):
        content = content.strip()
        
        # 跳过空内容
        if not content:
            continue
        
        # 移除第二个及后续内容的头部信息（标题、标签等）
        if i > 0:
            # 查找第一个二级标题，从那里开始提取内容
            header_match = re.search(r'\n## ', content)
            if header_match:
                content = content[header_match.start():].strip()
            else:
                # 如果没有找到二级标题，查找第一个有意义的内容行
                lines = content.split('\n')
                content_start = 0
                for j, line in enumerate(lines):
                    if line.strip() and not line.startswith('#') and not line.startswith('视频标题') and not line.startswith('视频标签'):
                        content_start = j
                        break
                content = '\n'.join(lines[content_start:]).strip()
        
        # 为每个分块添加分节标识
        if i > 0:  # 第一个分块不需要额外标识
            merged_content.append(f"\n\n## 第 {section_counter} 部分（续）\n")
            section_counter += 1
        
        # 添加内容，但移除开头的标题信息
        if i == 0:
            # 第一个内容，查找第一个二级标题开始的地方
            header_match = re.search(r'\n## ', content)
            if header_match:
                main_content = content[header_match.start():].strip()
                merged_content.append(main_content)
            else:
                merged_content.append(content)
        else:
            merged_content.append(content)
    
    # 添加合并说明
    merged_content.append(f"\n\n---\n\n## 📋 生成说明\n\n本笔记由于内容较长，采用了分块处理并合并生成。共处理了 {len(contents)} 个内容分块。")
    
    result = '\n'.join(merged_content)
    logger.info(f"✅ 内容合并完成，最终长度: {len(result)} 字符")
    
    return result


def create_chunk_summary_prompt(chunk_index: int, total_chunks: int, is_first: bool = False, is_last: bool = False) -> str:
    """
    为分块处理创建特殊的prompt说明
    
    Args:
        chunk_index: 当前分块索引（从1开始）
        total_chunks: 总分块数
        is_first: 是否为第一个分块
        is_last: 是否为最后一个分块
    
    Returns:
        分块处理的prompt说明
    """
    prompt_parts = []
    
    if is_first:
        prompt_parts.append(f"""
📋 **内容分块处理说明**：
由于视频内容较长，本次处理采用分块模式。这是第 {chunk_index}/{total_chunks} 部分。

对于第一部分，请：
1. 生成完整的笔记开头（包括标题、概述等）
2. 处理这部分的详细内容
3. 保持正常的markdown结构
""")
    elif is_last:
        prompt_parts.append(f"""
📋 **内容分块处理说明**：
这是第 {chunk_index}/{total_chunks} 部分（最后一部分）。

对于最后部分，请：
1. 处理这部分的详细内容
2. 在末尾生成完整的总结
3. 不需要重复标题信息
""")
    else:
        prompt_parts.append(f"""
📋 **内容分块处理说明**：
这是第 {chunk_index}/{total_chunks} 部分（中间部分）。

对于中间部分，请：
1. 直接处理内容，不需要重复标题
2. 保持与前后部分的连贯性
3. 重点关注这部分的核心内容
""")
    
    return '\n'.join(prompt_parts)