#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BaiduPCS-Py 下载器配置
基于官方文档的最佳实践配置
"""

from typing import Dict, List, Tuple
from enum import Enum


class DownloaderType(Enum):
    """下载器类型"""
    AUTO = "auto"           # 自动选择
    ME = "me"              # 推荐用于大文件
    AGET_PY = "aget_py"    # 推荐用于大文件
    AGET_RS = "aget_rs"    # 推荐用于大文件
    ARIA2 = "aria2"        # 小文件可用，大文件可能失败


class BaiduPCSConfig:
    """BaiduPCS-Py 配置管理"""
    
    # 文件大小阈值
    SMALL_FILE_THRESHOLD = 5 * 1024 * 1024   # 5MB
    MEDIUM_FILE_THRESHOLD = 10 * 1024 * 1024  # 10MB
    LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100MB
    
    # 官方建议的下载器优先级
    DOWNLOADERS_FOR_LARGE_FILES = [
        DownloaderType.ME,
        DownloaderType.AGET_RS,
        DownloaderType.AGET_PY
    ]
    
    DOWNLOADERS_FOR_SMALL_FILES = [
        DownloaderType.ME,
        DownloaderType.AGET_RS,
        DownloaderType.AGET_PY,
        DownloaderType.ARIA2
    ]
    
    # chunk_size配置（不能超过5M）
    CHUNK_SIZES = {
        "small": "512K",    # 小文件
        "medium": "1M",     # 中等文件
        "large": "2M",      # 大文件
        "max": "5M"         # 最大允许值
    }
    
    # 并发数配置
    CONCURRENCY = {
        "low": 1,      # 低并发
        "medium": 3,   # 中等并发
        "high": 5,     # 高并发
        "max": 8       # 最大并发
    }
    
    # 分块下载配置
    CHUNKED_DOWNLOAD = {
        "auto_threshold_mb": 10,    # 大于10MB自动启用分块下载
        "default_chunk_size_mb": 4, # 默认分块大小4MB
        "max_chunk_size_mb": 5,     # 最大分块大小5MB (百度限制)
        "min_chunk_size_mb": 1,     # 最小分块大小1MB
        "chunk_retry_times": 3,     # 分块重试次数
        "chunk_retry_delay": 0.5,   # 分块重试延迟(秒)
        "progress_report_interval": 1024 * 1024,  # 进度报告间隔(1MB)
    }
    
    @classmethod
    def get_optimal_config(cls, file_size: int) -> Dict[str, any]:
        """
        根据文件大小获取最优配置
        
        Args:
            file_size: 文件大小（字节）
            
        Returns:
            Dict: 配置信息
        """
        config = {
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "is_large_file": file_size > cls.SMALL_FILE_THRESHOLD
        }
        
        if file_size > cls.LARGE_FILE_THRESHOLD:
            # 超大文件 (>100MB)
            config.update({
                "category": "xlarge",
                "preferred_downloaders": [d.value for d in cls.DOWNLOADERS_FOR_LARGE_FILES],
                "chunk_size": cls.CHUNK_SIZES["large"],
                "concurrency": cls.CONCURRENCY["medium"],
                "timeout": 1800,  # 30分钟
                "notes": "超大文件，使用me/aget_rs/aget_py，避免aria2"
            })
        elif file_size > cls.MEDIUM_FILE_THRESHOLD:
            # 大文件 (10MB-100MB)
            config.update({
                "category": "large",
                "preferred_downloaders": [d.value for d in cls.DOWNLOADERS_FOR_LARGE_FILES],
                "chunk_size": cls.CHUNK_SIZES["medium"],
                "concurrency": cls.CONCURRENCY["medium"],
                "timeout": 900,   # 15分钟
                "notes": "大文件，推荐me/aget_rs/aget_py"
            })
        elif file_size > cls.SMALL_FILE_THRESHOLD:
            # 中等文件 (5MB-10MB)
            config.update({
                "category": "medium",
                "preferred_downloaders": [d.value for d in cls.DOWNLOADERS_FOR_LARGE_FILES],
                "chunk_size": cls.CHUNK_SIZES["small"],
                "concurrency": cls.CONCURRENCY["high"],
                "timeout": 600,   # 10分钟
                "notes": "中等文件，推荐me/aget_rs/aget_py"
            })
        else:
            # 小文件 (<5MB)
            config.update({
                "category": "small",
                "preferred_downloaders": [d.value for d in cls.DOWNLOADERS_FOR_SMALL_FILES],
                "chunk_size": cls.CHUNK_SIZES["small"],
                "concurrency": cls.CONCURRENCY["high"],
                "timeout": 300,   # 5分钟
                "notes": "小文件，可使用所有下载器"
            })
        
        return config
    
    @classmethod
    def get_fallback_strategies(cls) -> List[Dict[str, any]]:
        """
        获取备用下载策略
        
        Returns:
            List[Dict]: 备用策略列表
        """
        return [
            {
                "name": "conservative",
                "downloader": DownloaderType.ME.value,
                "chunk_size": "512K",
                "concurrency": 1,
                "description": "保守策略：使用me下载器，小块，低并发"
            },
            {
                "name": "balanced",
                "downloader": DownloaderType.AGET_RS.value,
                "chunk_size": "1M",
                "concurrency": 3,
                "description": "平衡策略：使用aget_rs，中等配置"
            },
            {
                "name": "aggressive",
                "downloader": DownloaderType.AGET_PY.value,
                "chunk_size": "2M",
                "concurrency": 5,
                "description": "激进策略：使用aget_py，大块，高并发"
            }
        ]
    
    @classmethod
    def validate_chunk_size(cls, chunk_size: str) -> Tuple[bool, str]:
        """
        验证chunk_size是否符合限制
        
        Args:
            chunk_size: chunk大小字符串
            
        Returns:
            Tuple[bool, str]: (是否有效, 消息)
        """
        try:
            # 解析chunk_size
            chunk_size_upper = chunk_size.upper()
            if chunk_size_upper.endswith('K'):
                bytes_size = int(chunk_size_upper[:-1]) * 1024
            elif chunk_size_upper.endswith('M'):
                bytes_size = int(chunk_size_upper[:-1]) * 1024 * 1024
            elif chunk_size_upper.endswith('G'):
                bytes_size = int(chunk_size_upper[:-1]) * 1024 * 1024 * 1024
            else:
                bytes_size = int(chunk_size_upper)
            
            # 检查是否超过5M限制
            max_bytes = 5 * 1024 * 1024  # 5M
            if bytes_size > max_bytes:
                return False, f"chunk_size({chunk_size})超过5M限制，请使用≤5M的值"
            
            return True, "chunk_size有效"
            
        except Exception as e:
            return False, f"无效的chunk_size格式: {chunk_size}"
    
    @classmethod
    def get_chunked_download_config(cls, file_size: int) -> Dict[str, any]:
        """
        获取分块下载配置
        
        Args:
            file_size: 文件大小（字节）
            
        Returns:
            Dict: 分块下载配置
        """
        file_size_mb = file_size / (1024 * 1024)
        
        config = {
            "file_size": file_size,
            "file_size_mb": round(file_size_mb, 2),
            "should_use_chunked": file_size_mb > cls.CHUNKED_DOWNLOAD["auto_threshold_mb"],
            "chunk_size_mb": cls.CHUNKED_DOWNLOAD["default_chunk_size_mb"],
            "estimated_chunks": max(1, int(file_size_mb / cls.CHUNKED_DOWNLOAD["default_chunk_size_mb"])),
            "retry_config": {
                "max_retries": cls.CHUNKED_DOWNLOAD["chunk_retry_times"],
                "retry_delay": cls.CHUNKED_DOWNLOAD["chunk_retry_delay"]
            }
        }
        
        # 根据文件大小调整分块策略
        if file_size_mb > 500:  # 大于500MB的超大文件
            config.update({
                "category": "ultra_large",
                "chunk_size_mb": cls.CHUNKED_DOWNLOAD["max_chunk_size_mb"],  # 使用最大分块
                "timeout_per_chunk": 120,  # 每个分块2分钟超时
                "notes": "超大文件，使用5MB分块，延长超时时间"
            })
        elif file_size_mb > 100:  # 大于100MB的大文件
            config.update({
                "category": "large",
                "chunk_size_mb": cls.CHUNKED_DOWNLOAD["default_chunk_size_mb"],
                "timeout_per_chunk": 60,   # 每个分块1分钟超时
                "notes": "大文件，使用4MB分块"
            })
        elif file_size_mb > cls.CHUNKED_DOWNLOAD["auto_threshold_mb"]:  # 中等文件
            config.update({
                "category": "medium",
                "chunk_size_mb": cls.CHUNKED_DOWNLOAD["default_chunk_size_mb"],
                "timeout_per_chunk": 30,   # 每个分块30秒超时
                "notes": "中等文件，使用4MB分块"
            })
        else:  # 小文件
            config.update({
                "category": "small",
                "should_use_chunked": False,
                "chunk_size_mb": cls.CHUNKED_DOWNLOAD["min_chunk_size_mb"],
                "timeout_per_chunk": 15,   # 每个分块15秒超时
                "notes": "小文件，建议使用常规下载"
            })
        
        # 重新计算预估分块数
        config["estimated_chunks"] = max(1, int(file_size_mb / config["chunk_size_mb"]))
        config["estimated_time_minutes"] = config["estimated_chunks"] * 0.5  # 假设每个分块0.5分钟
        
        return config
    
    @classmethod
    def validate_chunk_size_mb(cls, chunk_size_mb: int) -> Tuple[bool, str]:
        """
        验证分块大小是否有效
        
        Args:
            chunk_size_mb: 分块大小（MB）
            
        Returns:
            Tuple[bool, str]: (是否有效, 消息)
        """
        if chunk_size_mb < cls.CHUNKED_DOWNLOAD["min_chunk_size_mb"]:
            return False, f"分块大小不能小于{cls.CHUNKED_DOWNLOAD['min_chunk_size_mb']}MB"
        
        if chunk_size_mb > cls.CHUNKED_DOWNLOAD["max_chunk_size_mb"]:
            return False, f"分块大小不能大于{cls.CHUNKED_DOWNLOAD['max_chunk_size_mb']}MB (百度服务限制)"
        
        return True, "分块大小有效"
    
    @classmethod
    def get_recommended_settings(cls) -> Dict[str, any]:
        """
        获取推荐设置
        
        Returns:
            Dict: 推荐设置
        """
        base_settings = {
            "default_downloader": DownloaderType.AUTO.value,
            "default_chunk_size": "auto",
            "default_concurrency": cls.CONCURRENCY["medium"],
            "retry_times": 3,
            "retry_delay": 2,  # 秒
            "use_fallback": True,
            "log_level": "INFO",
            # 分块下载设置
            "chunked_download": {
                "auto_enable_threshold_mb": cls.CHUNKED_DOWNLOAD["auto_threshold_mb"],
                "default_chunk_size_mb": cls.CHUNKED_DOWNLOAD["default_chunk_size_mb"],
                "enable_progress_logging": True,
                "enable_chunk_retry": True
            },
            "tips": [
                "🎯 使用auto模式可自动选择最佳配置",
                "📏 chunk_size不能超过5M (百度服务限制)",
                "🚀 大于5MB文件推荐使用me/aget_py/aget_rs",
                "⚠️ aria2对大文件可能失败，建议避免",
                "🔄 失败时会自动尝试备用下载器",
                "⏱️ 下载超时会根据文件大小自动调整",
                "🧩 大于10MB文件自动启用分块下载(4MB每块)",
                "📊 分块下载提供详细的进度和错误日志",
                "🔧 分块下载支持断点续传和错误恢复"
            ]
        }
        
        return base_settings


# 全局配置实例
baidupcs_config = BaiduPCSConfig()


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}PB"


def get_download_config_summary(file_size: int) -> str:
    """获取下载配置摘要"""
    config = BaiduPCSConfig.get_optimal_config(file_size)
    
    summary = f"""
📊 文件下载配置摘要
├─ 文件大小: {format_file_size(file_size)} ({config['category']})
├─ 推荐下载器: {', '.join(config['preferred_downloaders'])}
├─ Chunk大小: {config['chunk_size']}
├─ 并发数: {config['concurrency']}
├─ 超时时间: {config['timeout']}s
└─ 备注: {config['notes']}
"""
    return summary.strip()


def get_chunked_download_summary(file_size: int) -> str:
    """获取分块下载配置摘要"""
    config = BaiduPCSConfig.get_chunked_download_config(file_size)
    
    summary = f"""
🧩 分块下载配置摘要
├─ 文件大小: {format_file_size(file_size)} ({config['category']})
├─ 启用分块下载: {'✅' if config['should_use_chunked'] else '❌'}
├─ 分块大小: {config['chunk_size_mb']}MB
├─ 预估分块数: {config['estimated_chunks']}
├─ 预估时间: {config['estimated_time_minutes']:.1f}分钟
├─ 单块超时: {config['timeout_per_chunk']}秒
├─ 重试配置: {config['retry_config']['max_retries']}次, {config['retry_config']['retry_delay']}s延迟
└─ 备注: {config['notes']}
"""
    return summary.strip()


def compare_download_methods(file_size: int) -> str:
    """比较不同下载方法的建议"""
    regular_config = BaiduPCSConfig.get_optimal_config(file_size)
    chunked_config = BaiduPCSConfig.get_chunked_download_config(file_size)
    
    comparison = f"""
📊 下载方法比较 (文件大小: {format_file_size(file_size)})

🔧 常规下载:
├─ 推荐下载器: {', '.join(regular_config['preferred_downloaders'])}
├─ Chunk大小: {regular_config['chunk_size']}
├─ 并发数: {regular_config['concurrency']}
├─ 超时时间: {regular_config['timeout']}秒
└─ 适用场景: {regular_config['notes']}

🧩 分块下载:
├─ 是否推荐: {'✅ 推荐' if chunked_config['should_use_chunked'] else '❌ 不推荐'}
├─ 分块大小: {chunked_config['chunk_size_mb']}MB
├─ 预估分块数: {chunked_config['estimated_chunks']}
├─ 单块超时: {chunked_config['timeout_per_chunk']}秒
└─ 适用场景: {chunked_config['notes']}

💡 建议:
{get_download_recommendation(file_size)}
"""
    return comparison.strip()


def get_download_recommendation(file_size: int) -> str:
    """获取下载建议"""
    file_size_mb = file_size / (1024 * 1024)
    
    if file_size_mb < 5:
        return "小文件，推荐使用常规下载，所有下载器都可用"
    elif file_size_mb < 10:
        return "中小文件，推荐使用常规下载，避免aria2下载器"
    elif file_size_mb < 100:
        return "中等文件，推荐使用分块下载，提高稳定性和可监控性"
    elif file_size_mb < 500:
        return "大文件，强烈推荐使用分块下载，提供断点续传能力"
    else:
        return "超大文件，必须使用分块下载，使用5MB分块提高效率"


if __name__ == "__main__":
    # 测试配置
    test_sizes = [
        1024 * 1024,        # 1MB
        3 * 1024 * 1024,    # 3MB
        10 * 1024 * 1024,   # 10MB
        50 * 1024 * 1024,   # 50MB
        200 * 1024 * 1024,  # 200MB
        1024 * 1024 * 1024  # 1GB
    ]
    
    print("📋 BaiduPCS-Py 下载配置测试")
    print("=" * 50)
    
    for size in test_sizes:
        print(f"\n{get_download_config_summary(size)}")
        print(f"\n{get_chunked_download_summary(size)}")
        print(f"\n{compare_download_methods(size)}")
        print("-" * 50)
    
    print("\n🛠️ 推荐设置:")
    recommended = BaiduPCSConfig.get_recommended_settings()
    for key, value in recommended.items():
        if key != "tips" and key != "chunked_download":
            print(f"├─ {key}: {value}")
    
    print("\n🧩 分块下载设置:")
    chunked_settings = recommended["chunked_download"]
    for key, value in chunked_settings.items():
        print(f"├─ {key}: {value}")
    
    print("\n💡 使用提示:")
    for tip in recommended["tips"]:
        print(f"  {tip}") 