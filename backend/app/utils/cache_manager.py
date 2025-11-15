#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
缓存管理器
提供LRU缓存功能，用于缓存百度网盘文件列表等数据
"""

from typing import Any, Optional, Callable
from functools import lru_cache
import time
import hashlib
import json
from collections import OrderedDict
from threading import Lock
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TTLCache:
    """
    带TTL(Time-To-Live)的LRU缓存
    支持过期时间，自动清理过期数据
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间(秒)，默认5分钟
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
        
        logger.info(f"🚀 初始化TTL缓存: max_size={max_size}, default_ttl={default_ttl}秒")
    
    def _is_expired(self, entry: dict) -> bool:
        """检查缓存条目是否过期"""
        return time.time() > entry['expire_time']
    
    def _cleanup_expired(self):
        """清理过期条目"""
        current_time = time.time()
        expired_keys = []
        
        for key, entry in self._cache.items():
            if current_time > entry['expire_time']:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            logger.debug(f"🧹 清理了 {len(expired_keys)} 个过期缓存条目")
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存的值，如果不存在或已过期则返回None
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                logger.debug(f"❌ 缓存未命中: {key}")
                return None
            
            entry = self._cache[key]
            
            # 检查是否过期
            if self._is_expired(entry):
                del self._cache[key]
                self._misses += 1
                logger.debug(f"⏰ 缓存已过期: {key}")
                return None
            
            # 移动到最后（LRU更新）
            self._cache.move_to_end(key)
            self._hits += 1
            logger.debug(f"✅ 缓存命中: {key}")
            return entry['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间(秒)，None则使用默认值
        """
        with self._lock:
            # 清理过期条目
            self._cleanup_expired()
            
            # 如果达到最大容量，删除最旧的条目
            if len(self._cache) >= self.max_size and key not in self._cache:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                logger.debug(f"🗑️ 缓存已满，删除最旧条目: {oldest_key}")
            
            expire_time = time.time() + (ttl if ttl is not None else self.default_ttl)
            
            self._cache[key] = {
                'value': value,
                'expire_time': expire_time,
                'created_at': time.time()
            }
            
            # 移动到最后
            self._cache.move_to_end(key)
            logger.debug(f"💾 缓存已设置: {key}, TTL={ttl if ttl else self.default_ttl}秒")
    
    def delete(self, key: str):
        """删除缓存条目"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"🗑️ 缓存已删除: {key}")
    
    def clear(self):
        """清空所有缓存"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info(f"🧹 清空缓存: 删除了 {count} 个条目")
    
    def stats(self) -> dict:
        """获取缓存统计信息"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': f"{hit_rate:.2f}%",
                'total_requests': total
            }


class CacheManager:
    """
    缓存管理器
    统一管理各种缓存实例
    """
    
    def __init__(self):
        # 百度网盘文件列表缓存（较长TTL）
        self.baidu_pan_file_list_cache = TTLCache(max_size=500, default_ttl=300)  # 5分钟
        
        # 用户信息缓存
        self.user_info_cache = TTLCache(max_size=100, default_ttl=600)  # 10分钟
        
        # 通用缓存
        self.general_cache = TTLCache(max_size=1000, default_ttl=180)  # 3分钟
        
        logger.info("✅ 缓存管理器初始化完成")
    
    def get_cache(self, cache_type: str = 'general') -> TTLCache:
        """
        获取指定类型的缓存实例
        
        Args:
            cache_type: 缓存类型，可选值: 'baidu_pan_file_list', 'user_info', 'general'
        """
        cache_map = {
            'baidu_pan_file_list': self.baidu_pan_file_list_cache,
            'user_info': self.user_info_cache,
            'general': self.general_cache
        }
        
        return cache_map.get(cache_type, self.general_cache)
    
    def clear_all(self):
        """清空所有缓存"""
        self.baidu_pan_file_list_cache.clear()
        self.user_info_cache.clear()
        self.general_cache.clear()
        logger.info("🧹 已清空所有缓存")
    
    def get_all_stats(self) -> dict:
        """获取所有缓存的统计信息"""
        return {
            'baidu_pan_file_list': self.baidu_pan_file_list_cache.stats(),
            'user_info': self.user_info_cache.stats(),
            'general': self.general_cache.stats()
        }


# 全局缓存管理器实例
cache_manager = CacheManager()


def generate_cache_key(*args, **kwargs) -> str:
    """
    生成缓存键
    
    Args:
        *args: 位置参数
        **kwargs: 关键字参数
        
    Returns:
        MD5哈希值作为缓存键
    """
    # 将参数转换为字符串
    key_parts = [str(arg) for arg in args]
    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
    key_string = "|".join(key_parts)
    
    # 生成MD5哈希
    return hashlib.md5(key_string.encode('utf-8')).hexdigest()


def cached(cache_type: str = 'general', ttl: Optional[int] = None, key_prefix: str = ''):
    """
    缓存装饰器
    
    Args:
        cache_type: 缓存类型
        ttl: 过期时间(秒)
        key_prefix: 缓存键前缀
        
    Example:
        @cached(cache_type='baidu_pan_file_list', ttl=300, key_prefix='file_list')
        def get_file_list(path: str):
            # 函数逻辑
            pass
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{generate_cache_key(*args, **kwargs)}"
            
            # 尝试从缓存获取
            cache = cache_manager.get_cache(cache_type)
            cached_value = cache.get(cache_key)
            
            if cached_value is not None:
                logger.debug(f"✅ 使用缓存: {func.__name__}")
                return cached_value
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 保存到缓存
            cache.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


# 便捷函数
def get_baidu_pan_cache() -> TTLCache:
    """获取百度网盘文件列表缓存"""
    return cache_manager.baidu_pan_file_list_cache


def clear_baidu_pan_cache():
    """清空百度网盘缓存"""
    cache_manager.baidu_pan_file_list_cache.clear()
    logger.info("🧹 已清空百度网盘文件列表缓存")

