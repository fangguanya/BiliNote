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
    # - 中文字符按2.0个token计算（之前1.5偏小）
    # - 英文单词按1.3个token计算（考虑子词分割）
    # - 其他字符按0.8个token计算
    # - 再加20%的安全余量
    estimated_tokens = int((chinese_chars * 2.0 + english_words * 1.3 + other_chars * 0.8) * 1.2)
    
    logger.debug(f"📊 Token估算详情: 总字符={total_chars}, 中文={chinese_chars}, 英文单词={english_words}, 其他={other_chars}, 估算tokens={estimated_tokens}")
    
    return estimated_tokens


def estimate_image_tokens_from_base64(image_urls: list) -> int:
    """
    根据图片base64字符串估算token数量
    base64编码的图片在LLM中通常按字符数/4来估算token（base64编码约为原始数据的4/3）
    """
    if not image_urls:
        return 0
    
    total_tokens = 0
    for image_url in image_urls:
        if isinstance(image_url, str) and image_url.startswith('data:image/'):
            # 提取base64部分 (去掉 "data:image/jpeg;base64," 前缀)
            base64_part = image_url.split(',', 1)[-1] if ',' in image_url else image_url
            
            # base64字符数量估算token（经验公式：base64字符数 / 3）
            base64_tokens = len(base64_part) // 15
            total_tokens += base64_tokens
            
            logger.debug(f"📸 图片token估算: base64长度={len(base64_part)}, 估算tokens={base64_tokens}")
        else:
            # 非base64图片，按固定token估算
            total_tokens += 500
            logger.debug(f"📸 非base64图片，固定估算500 tokens")
    
    logger.info(f"📊 图片总token估算: {len(image_urls)}张图片, 总计{total_tokens} tokens")
    return total_tokens


def estimate_mixed_content_tokens(text: str, image_urls: list = None) -> int:
    """
    估算包含文本和图片的混合内容token数量
    """
    text_tokens = estimate_tokens(text) if text else 0
    image_tokens = estimate_image_tokens_from_base64(image_urls or [])
    total_tokens = text_tokens + image_tokens
    
    logger.info(f"📊 混合内容token估算: 文本={text_tokens}, 图片={image_tokens}, 总计={total_tokens}")
    return total_tokens


def split_segments_with_images_by_tokens(
    segments: List[TranscriptSegment], 
    image_urls: List[str] = None,
    max_tokens: int = 80000
) -> List[Tuple[List[TranscriptSegment], List[str]]]:
    """
    根据token限制将转录片段和图片分割成多个组，图片可以分散到不同分块
    
    Args:
        segments: 转录片段列表
        image_urls: 图片URL列表
        max_tokens: 每组的最大token数
    
    Returns:
        分割后的(片段组, 图片组)元组列表
    """
    if not segments:
        return []
    
    chunks = []
    current_chunk = []
    current_images = []
    current_tokens = 0
    
    # 为prompt模板预留token空间
    template_reserve = 10000
    actual_max_tokens = max_tokens - template_reserve
    
    # 计算图片token信息
    image_urls = image_urls or []
    image_tokens_list = []  # 每张图片的token数
    total_image_tokens = 0
    
    for image_url in image_urls:
        tokens = estimate_image_tokens_from_base64([image_url])
        image_tokens_list.append(tokens)
        total_image_tokens += tokens
    
    logger.info(f"📊 开始混合内容分割: 转录片段={len(segments)}, 图片={len(image_urls)}, 图片总tokens={total_image_tokens}")
    logger.info(f"📊 最大token数: {actual_max_tokens} (预留: {template_reserve})")
    
    # 如果没有图片，使用原有的分块逻辑
    if not image_urls:
        segment_chunks = split_segments_by_tokens(segments, max_tokens)
        return [(chunk, []) for chunk in segment_chunks]
    
    # 创建图片队列，用于分配
    available_images = list(zip(image_urls, image_tokens_list))
    image_queue_index = 0
    
    for i, segment in enumerate(segments):
        segment_text = f"{format_time_from_seconds(segment.start)} - {segment.text.strip()}"
        segment_tokens = estimate_tokens(segment_text)
        
        # 尝试从图片队列中添加图片到当前分块
        while image_queue_index < len(available_images):
            next_image_url, next_image_tokens = available_images[image_queue_index]
            
            # 检查当前分块是否能容纳这张图片
            potential_tokens = current_tokens + segment_tokens + next_image_tokens
            current_image_tokens = sum(tokens for _, tokens in current_images)
            potential_total = current_tokens + segment_tokens + current_image_tokens + next_image_tokens
            
            if potential_total <= actual_max_tokens:
                # 可以添加这张图片
                current_images.append((next_image_url, next_image_tokens))
                image_queue_index += 1
                logger.debug(f"📸 添加图片到分块 {len(chunks)+1}: {next_image_tokens} tokens")
            else:
                # 当前分块无法容纳更多图片，停止添加
                break
        
        # 检查当前片段是否可以添加到当前分块
        current_image_tokens = sum(tokens for _, tokens in current_images)
        total_current_tokens = current_tokens + segment_tokens + current_image_tokens
        
        if total_current_tokens > actual_max_tokens and current_chunk:
            # 当前分块已满，保存并开始新分块
            final_images = [img_url for img_url, _ in current_images]
            chunks.append((current_chunk, final_images))
            
            total_tokens = current_tokens + current_image_tokens
            logger.info(f"📦 完成分块 {len(chunks)}: {len(current_chunk)}个片段, {len(final_images)}张图片, {current_tokens}文本+{current_image_tokens}图片={total_tokens} tokens")
            
            # 开始新分块
            current_chunk = [segment]
            current_images = []
            current_tokens = segment_tokens
        else:
            # 添加片段到当前分块
            current_chunk.append(segment)
            current_tokens += segment_tokens
    
    # 如果还有剩余的图片未分配，尝试分配到最后一个分块或创建新分块
    while image_queue_index < len(available_images):
        remaining_images = available_images[image_queue_index:]
        remaining_image_tokens = sum(tokens for _, tokens in remaining_images)
        
        current_image_tokens = sum(tokens for _, tokens in current_images)
        total_current_tokens = current_tokens + current_image_tokens + remaining_image_tokens
        
        if total_current_tokens <= actual_max_tokens:
            # 所有剩余图片都可以加入当前分块
            current_images.extend(remaining_images)
            image_queue_index = len(available_images)
            logger.info(f"📸 将剩余 {len(remaining_images)} 张图片添加到最后分块")
        else:
            # 需要为剩余图片创建新分块，尝试逐张添加
            while image_queue_index < len(available_images):
                next_image_url, next_image_tokens = available_images[image_queue_index]
                current_image_tokens = sum(tokens for _, tokens in current_images)
                
                if current_tokens + current_image_tokens + next_image_tokens <= actual_max_tokens:
                    current_images.append((next_image_url, next_image_tokens))
                    image_queue_index += 1
                else:
                    # 当前分块无法容纳，结束当前分块，为剩余图片创建新分块
                    break
            
            # 如果还有未分配的图片，为它们创建新的分块
            if image_queue_index < len(available_images):
                # 保存当前分块
                if current_chunk:
                    final_images = [img_url for img_url, _ in current_images]
                    chunks.append((current_chunk, final_images))
                    
                    current_image_tokens = sum(tokens for _, tokens in current_images)
                    total_tokens = current_tokens + current_image_tokens
                    logger.info(f"📦 完成分块 {len(chunks)}: {len(current_chunk)}个片段, {len(final_images)}张图片, {current_tokens}文本+{current_image_tokens}图片={total_tokens} tokens")
                
                # 为剩余图片创建新分块（只包含图片，不包含转录）
                remaining_images = available_images[image_queue_index:]
                remaining_chunk_images = []
                remaining_tokens = 0
                
                for img_url, img_tokens in remaining_images:
                    if remaining_tokens + img_tokens <= actual_max_tokens:
                        remaining_chunk_images.append(img_url)
                        remaining_tokens += img_tokens
                    else:
                        # 如果还有图片装不下，需要进一步分块
                        if remaining_chunk_images:
                            chunks.append(([], remaining_chunk_images))
                            logger.info(f"📦 完成图片分块 {len(chunks)}: 0个片段, {len(remaining_chunk_images)}张图片, {remaining_tokens} tokens")
                        
                        remaining_chunk_images = [img_url]
                        remaining_tokens = img_tokens
                
                # 添加最后的图片分块
                if remaining_chunk_images:
                    chunks.append(([], remaining_chunk_images))
                    logger.info(f"📦 完成最后图片分块 {len(chunks)}: 0个片段, {len(remaining_chunk_images)}张图片, {remaining_tokens} tokens")
                
                image_queue_index = len(available_images)
                current_chunk = []
                current_images = []
                current_tokens = 0
    
    # 添加最后一个分块（如果有内容）
    if current_chunk or current_images:
        final_images = [img_url for img_url, _ in current_images]
        chunks.append((current_chunk, final_images))
        
        current_image_tokens = sum(tokens for _, tokens in current_images)
        total_tokens = current_tokens + current_image_tokens
        logger.info(f"📦 完成最后分块 {len(chunks)}: {len(current_chunk)}个片段, {len(final_images)}张图片, {current_tokens}文本+{current_image_tokens}图片={total_tokens} tokens")
    
    logger.info(f"✅ 分块完成，共 {len(chunks)} 个分块，图片分配情况:")
    for i, (chunk_segments, chunk_images) in enumerate(chunks):
        logger.info(f"   分块{i+1}: {len(chunk_segments)}个片段, {len(chunk_images)}张图片")
    
    return chunks


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