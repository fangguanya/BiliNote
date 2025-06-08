import time
import functools
from typing import Any, Callable
from openai import APIError, RateLimitError
from app.utils.logger import get_logger

logger = get_logger(__name__)

def retry_on_rate_limit(max_retries: int = 3, delay: float = 30.0, backoff_factor: float = 1.5):
    """
    装饰器：处理LLM API的429 Rate Limit错误，自动重试
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff_factor: 退避因子，每次重试延迟时间的倍数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):  # +1 因为第一次不算重试
                try:
                    return func(*args, **kwargs)
                    
                except RateLimitError as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"🔄 API速率限制，第{attempt + 1}次重试，等待{current_delay}秒...")
                        logger.warning(f"错误信息: {str(e)}")
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                        continue
                    else:
                        logger.error(f"❌ API速率限制，已达到最大重试次数({max_retries})，放弃重试")
                        raise
                        
                except APIError as e:
                    # 检查是否是429错误
                    if hasattr(e, 'status_code') and e.status_code == 429:
                        last_exception = e
                        if attempt < max_retries:
                            logger.warning(f"🔄 API速率限制(429)，第{attempt + 1}次重试，等待{current_delay}秒...")
                            logger.warning(f"错误信息: {str(e)}")
                            time.sleep(current_delay)
                            current_delay *= backoff_factor
                            continue
                        else:
                            logger.error(f"❌ API速率限制(429)，已达到最大重试次数({max_retries})，放弃重试")
                            raise
                    else:
                        # 其他API错误直接抛出
                        raise
                        
                except Exception as e:
                    # 检查错误消息中是否包含429相关信息
                    error_msg = str(e).lower()
                    if ('429' in error_msg or 'rate limit' in error_msg or 'too many requests' in error_msg 
                        or 'failed to schedule worker' in error_msg):
                        last_exception = e
                        if attempt < max_retries:
                            logger.warning(f"🔄 疑似速率限制错误，第{attempt + 1}次重试，等待{current_delay}秒...")
                            logger.warning(f"错误信息: {str(e)}")
                            time.sleep(current_delay)
                            current_delay *= backoff_factor
                            continue
                        else:
                            logger.error(f"❌ 疑似速率限制错误，已达到最大重试次数({max_retries})，放弃重试")
                            raise
                    else:
                        # 其他异常直接抛出
                        raise
                        
            # 如果到这里，说明所有重试都失败了
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator

def log_retry_attempt(attempt: int, max_retries: int, delay: float, error: str):
    """记录重试尝试的日志"""
    logger.warning(f"🔄 重试尝试 {attempt}/{max_retries}，延迟 {delay:.1f}s")
    logger.warning(f"错误原因: {error}")

def is_rate_limit_error(error: Exception) -> bool:
    """检查是否为速率限制错误"""
    if isinstance(error, RateLimitError):
        return True
    
    if isinstance(error, APIError) and hasattr(error, 'status_code') and error.status_code == 429:
        return True
    
    error_msg = str(error).lower()
    rate_limit_keywords = [
        '429', 'rate limit', 'too many requests', 
        'failed to schedule worker', 'quota exceeded',
        'requests per minute', 'tokens per minute'
    ]
    
    return any(keyword in error_msg for keyword in rate_limit_keywords) 