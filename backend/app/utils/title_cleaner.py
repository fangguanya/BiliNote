import re
from typing import Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)


def clean_collection_title(title: str, platform: str = "") -> str:
    """
    清理标题中的合集相关字符串，提取更简洁的标题
    
    :param title: 原始标题
    :param platform: 平台名称，用于特定平台的处理
    :return: 清理后的标题
    """
    if not title:
        return title
    
    original_title = title
    
    # 定义需要去掉的合集相关关键词和模式
    collection_patterns = [
        # 完整的合集标识
        r'【合集】',
        r'【系列】',
        r'【全集】',
        r'【连载】',
        
        # 带括号的合集标识
        r'\(合集\)',
        r'\(系列\)',
        r'\(全集\)',
        r'\(连载\)',
        
        # 直接的合集标识
        r'合集[：:]?\s*',
        r'系列[：:]?\s*',
        r'全集[：:]?\s*',
        r'连载[：:]?\s*',
        
        # 集数标识 - 但要保留单独的集数信息
        r'第\d+集[：:]?\s*',
        r'第\d+期[：:]?\s*',
        r'第\d+部分[：:]?\s*',
        r'第\d+章[：:]?\s*',
        
        # P系列（B站特有）
        r'^P\d+[：:\s]*',
        r'^\d+P[：:\s]*',
        
        # 英文集数标识
        r'^EP\.?\d+[：:\s]*',
        r'^Episode\s*\d+[：:\s]*',
        r'Season\s*\d+[：:\s]*',
        
        # 分隔符和编号
        r'^\d+[\.．][：:\s]*',  # 开头的数字编号
        r'^【\d+】[：:\s]*',    # 开头的数字编号（中文括号）
        r'^\[\d+\][：:\s]*',    # 开头的数字编号（英文括号）
        
        # 其他常见模式
        r'完整版[：:]?\s*',
        r'高清版[：:]?\s*',
        r'正式版[：:]?\s*',
        r'官方版[：:]?\s*',
        
        # 上下篇标识
        r'上篇[：:]?\s*',
        r'下篇[：:]?\s*',
        r'上集[：:]?\s*',
        r'下集[：:]?\s*',
        
        # 番外篇
        r'番外[：:]?\s*',
        r'特别篇[：:]?\s*',
        r'预告[：:]?\s*',
    ]
    
    # 应用所有清理模式
    for pattern in collection_patterns:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    
    # 清理多余的标点符号和空格
    title = re.sub(r'[：:\s]*$', '', title)  # 去掉末尾的冒号和空格
    title = re.sub(r'^[：:\s]*', '', title)  # 去掉开头的冒号和空格
    title = re.sub(r'\s+', ' ', title)      # 合并多个空格为单个空格
    title = title.strip()
    
    # 如果清理后的标题太短或为空，保留原标题
    if len(title) < 3:
        logger.warning(f"⚠️ 标题清理后过短，保留原标题: '{original_title}' -> '{title}'")
        return original_title
    
    # 如果标题发生了变化，记录日志
    if title != original_title:
        logger.info(f"🧹 标题清理完成: '{original_title}' -> '{title}'")
    
    return title


def extract_episode_info(title: str) -> tuple[str, Optional[str]]:
    """
    从标题中提取集数信息和清理后的标题
    
    :param title: 原始标题
    :return: (清理后的标题, 集数信息)
    """
    original_title = title
    episode_info = None
    
    # 提取集数信息的模式
    episode_patterns = [
        (r'第(\d+)集', lambda m: f"第{m.group(1)}集"),
        (r'第(\d+)期', lambda m: f"第{m.group(1)}期"),
        (r'第(\d+)部分', lambda m: f"第{m.group(1)}部分"),
        (r'第(\d+)章', lambda m: f"第{m.group(1)}章"),
        (r'^P(\d+)', lambda m: f"P{m.group(1)}"),
        (r'^(\d+)P', lambda m: f"P{m.group(1)}"),
        (r'^EP\.?(\d+)', lambda m: f"EP{m.group(1)}"),
        (r'^Episode\s*(\d+)', lambda m: f"Episode {m.group(1)}"),
        (r'^\d+[\.．]', lambda m: m.group(0).rstrip('．.')),
        (r'^【(\d+)】', lambda m: f"第{m.group(1)}集"),
        (r'^\[(\d+)\]', lambda m: f"第{m.group(1)}集"),
    ]
    
    # 尝试提取集数信息
    for pattern, formatter in episode_patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            episode_info = formatter(match)
            break
    
    # 清理标题
    cleaned_title = clean_collection_title(title)
    
    return cleaned_title, episode_info


def smart_title_clean(title: str, platform: str = "", preserve_episode: bool = True) -> str:
    """
    智能标题清理，可选择是否保留集数信息
    
    :param title: 原始标题
    :param platform: 平台名称
    :param preserve_episode: 是否保留集数信息
    :return: 清理后的标题
    """
    if not title:
        return title
    
    if preserve_episode:
        # 提取集数信息并清理标题
        cleaned_title, episode_info = extract_episode_info(title)
        
        # 如果有集数信息，可以选择是否加回去
        if episode_info and len(cleaned_title) > 3:
            # 通常情况下不加回去，除非特别需要
            return cleaned_title
        else:
            return cleaned_title
    else:
        # 直接清理，不保留集数信息
        return clean_collection_title(title, platform)


# 为兼容性提供别名
def clean_title(title: str, platform: str = "") -> str:
    """
    兼容性函数，调用智能标题清理
    """
    return smart_title_clean(title, platform, preserve_episode=False)


# 测试函数
def test_title_cleaning():
    """测试标题清理功能"""
    test_cases = [
        "【合集】Python编程教程",
        "合集：机器学习基础",
        "第1集：变量和数据类型",
        "P1 Python环境搭建",
        "EP01 深度学习入门",
        "【1】神经网络基础",
        "[02] 反向传播算法",
        "上篇：理论基础",
        "完整版 TensorFlow教程",
        "系列：AI开发实战",
        "番外篇：调试技巧",
        "Python编程入门教程 - 完整版",
        "Episode 5: Advanced Concepts",
        "Season 2 第3集：高级特性",
    ]
    
    print("=== 标题清理测试 ===")
    for test_title in test_cases:
        cleaned = smart_title_clean(test_title)
        cleaned_with_episode, episode = extract_episode_info(test_title)
        print(f"原标题: {test_title}")
        print(f"清理后: {cleaned}")
        print(f"带集数: {cleaned_with_episode} (集数: {episode})")
        print("-" * 50)


if __name__ == "__main__":
    test_title_cleaning() 