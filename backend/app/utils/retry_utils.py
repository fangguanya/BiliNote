import time
import functools
from typing import Any, Callable
from openai import APIError, RateLimitError, APIConnectionError, APITimeoutError
from app.utils.logger import get_logger
import re

logger = get_logger(__name__)

def retry_on_rate_limit(max_retries: int = 3, delay: float = 30.0, backoff_factor: float = 1.5):
    """
    装饰器：处理LLM API的速率限制(RPM/TPM)和连接错误，自动重试
    
    Args:
        max_retries: 最大重试次数（默认3次）
        delay: 初始延迟时间（秒，默认30秒）
        backoff_factor: 退避因子，每次重试延迟时间的倍数（默认1.5倍）
        
    支持的错误类型：
        - RateLimitError: OpenAI 速率限制错误（RPM/TPM超限）
        - APIError 429: HTTP 429 Too Many Requests
        - APIConnectionError: 网络连接错误
        - APITimeoutError: 请求超时
        - 其他包含速率限制关键词的错误
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):  # +1 因为第一次不算重试
                try:
                    # 如果是重试，记录开始信息
                    if attempt > 0:
                        logger.info(f"🔄 开始第 {attempt} 次重试（共 {max_retries} 次）...")
                    
                    result = func(*args, **kwargs)
                    
                    # 如果成功且之前有重试，记录成功信息
                    if attempt > 0:
                        logger.info(f"✅ 重试成功！（第 {attempt} 次重试）")
                    
                    return result
                    
                except RateLimitError as e:
                    last_exception = e
                    error_type = "RPM/TPM 速率限制"
                    
                    # 尝试从错误信息中提取等待时间
                    retry_after = _extract_retry_after(str(e))
                    wait_time = retry_after if retry_after else current_delay
                    
                    if attempt < max_retries:
                        logger.warning(f"⚠️ {error_type} - 第 {attempt + 1}/{max_retries} 次重试")
                        logger.warning(f"📋 错误详情: {str(e)}")
                        if retry_after:
                            logger.warning(f"⏰ API 建议等待: {retry_after:.1f}秒")
                        logger.warning(f"⏳ 等待 {wait_time:.1f}秒 后重试...")
                        
                        time.sleep(wait_time)
                        current_delay *= backoff_factor
                        continue
                    else:
                        logger.error(f"❌ {error_type} - 已达到最大重试次数 ({max_retries})")
                        logger.error(f"💔 最终错误: {str(e)}")
                        raise
                        
                except APIConnectionError as e:
                    last_exception = e
                    error_type = "API 连接错误"
                    
                    if attempt < max_retries:
                        logger.warning(f"⚠️ {error_type} - 第 {attempt + 1}/{max_retries} 次重试")
                        logger.warning(f"📋 错误详情: {str(e)}")
                        logger.warning(f"⏳ 等待 {current_delay:.1f}秒 后重试...")
                        
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                        continue
                    else:
                        logger.error(f"❌ {error_type} - 已达到最大重试次数 ({max_retries})")
                        logger.error(f"💔 最终错误: {str(e)}")
                        raise
                        
                except APITimeoutError as e:
                    last_exception = e
                    error_type = "API 超时错误"
                    
                    if attempt < max_retries:
                        logger.warning(f"⚠️ {error_type} - 第 {attempt + 1}/{max_retries} 次重试")
                        logger.warning(f"📋 错误详情: {str(e)}")
                        logger.warning(f"⏳ 等待 {current_delay:.1f}秒 后重试...")
                        
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                        continue
                    else:
                        logger.error(f"❌ {error_type} - 已达到最大重试次数 ({max_retries})")
                        logger.error(f"💔 最终错误: {str(e)}")
                        raise
                        
                except APIError as e:
                    # 检查是否是429错误
                    if hasattr(e, 'status_code') and e.status_code == 429:
                        last_exception = e
                        error_type = "HTTP 429 速率限制"
                        
                        # 尝试从响应头中获取 Retry-After
                        retry_after = _extract_retry_after(str(e))
                        wait_time = retry_after if retry_after else current_delay
                        
                        if attempt < max_retries:
                            logger.warning(f"⚠️ {error_type} - 第 {attempt + 1}/{max_retries} 次重试")
                            logger.warning(f"📋 错误详情: {str(e)}")
                            if retry_after:
                                logger.warning(f"⏰ API 建议等待: {retry_after:.1f}秒")
                            logger.warning(f"⏳ 等待 {wait_time:.1f}秒 后重试...")
                            
                            time.sleep(wait_time)
                            current_delay *= backoff_factor
                            continue
                        else:
                            logger.error(f"❌ {error_type} - 已达到最大重试次数 ({max_retries})")
                            logger.error(f"💔 最终错误: {str(e)}")
                            raise
                    else:
                        # 其他API错误直接抛出
                        logger.error(f"❌ API错误 (非速率限制): {str(e)}")
                        raise
                        
                except Exception as e:
                    # 检查错误消息中是否包含速率限制相关信息
                    error_msg = str(e).lower()
                    rate_limit_keywords = [
                        '429', 'rate limit', 'too many requests', 
                        'failed to schedule worker', 'quota exceeded',
                        'requests per minute', 'tokens per minute',
                        'rpm', 'tpm', 'rate_limit_exceeded'
                    ]
                    
                    is_rate_limit = any(keyword in error_msg for keyword in rate_limit_keywords)
                    
                    if is_rate_limit:
                        last_exception = e
                        error_type = "疑似速率限制错误"
                        
                        if attempt < max_retries:
                            logger.warning(f"⚠️ {error_type} - 第 {attempt + 1}/{max_retries} 次重试")
                            logger.warning(f"📋 错误详情: {str(e)}")
                            logger.warning(f"⏳ 等待 {current_delay:.1f}秒 后重试...")
                            
                            time.sleep(current_delay)
                            current_delay *= backoff_factor
                            continue
                        else:
                            logger.error(f"❌ {error_type} - 已达到最大重试次数 ({max_retries})")
                            logger.error(f"💔 最终错误: {str(e)}")
                            raise
                    else:
                        # 其他异常直接抛出
                        logger.error(f"❌ 未知错误: {str(e)}")
                        raise
                        
            # 如果到这里，说明所有重试都失败了
            if last_exception:
                logger.error(f"💀 所有重试均失败，抛出最后一次异常")
                raise last_exception
                
        return wrapper
    return decorator

def _extract_retry_after(error_message: str) -> float:
    """
    从错误消息中提取 Retry-After 时间（秒）
    
    Args:
        error_message: 错误消息字符串
        
    Returns:
        float: 建议的等待时间（秒），如果无法提取则返回 None
    """
    # 常见的 Retry-After 模式
    patterns = [
        r'retry[_\s-]after[:\s]+(\d+\.?\d*)\s*s',  # retry-after: 30s 或 retry_after: 30.5s
        r'retry[_\s-]after[:\s]+(\d+)',             # retry-after: 30
        r'please.*?try.*?(\d+\.?\d*)\s*second',     # please try again in 30 seconds
        r'wait.*?(\d+\.?\d*)\s*second',             # wait 30 seconds
        r'retry.*?(\d+\.?\d*)\s*second',            # retry in 30 seconds
        r'(\d+\.?\d*)\s*second.*?retry',            # 30 seconds before retry
    ]
    
    error_lower = error_message.lower()
    
    for pattern in patterns:
        match = re.search(pattern, error_lower)
        if match:
            try:
                retry_time = float(match.group(1))
                logger.debug(f"🔍 从错误消息中提取到 Retry-After: {retry_time}秒")
                return retry_time
            except (ValueError, IndexError):
                continue
    
    return None


def log_retry_attempt(attempt: int, max_retries: int, delay: float, error: str):
    """记录重试尝试的日志"""
    logger.warning(f"🔄 重试尝试 {attempt}/{max_retries}，延迟 {delay:.1f}s")
    logger.warning(f"错误原因: {error}")


def is_rate_limit_error(error: Exception) -> bool:
    """
    检查是否为速率限制错误
    
    Args:
        error: 异常对象
        
    Returns:
        bool: 如果是速率限制错误返回 True
    """
    if isinstance(error, RateLimitError):
        return True
    
    if isinstance(error, APIError) and hasattr(error, 'status_code') and error.status_code == 429:
        return True
    
    error_msg = str(error).lower()
    rate_limit_keywords = [
        '429', 'rate limit', 'too many requests', 
        'failed to schedule worker', 'quota exceeded',
        'requests per minute', 'tokens per minute',
        'rpm', 'tpm', 'rate_limit_exceeded'
    ]
    
    return any(keyword in error_msg for keyword in rate_limit_keywords) 