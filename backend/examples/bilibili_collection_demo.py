#!/usr/bin/env python3
"""
B站合集处理功能演示
基于 bilibili-API-collect 项目的API文档改进的合集处理功能
支持登录cookie状态，可以访问私人收藏夹、稍后再看、需要会员的内容等
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.url_parser import (
    identify_platform, 
    is_collection_url, 
    extract_collection_videos,
    is_video_part_of_collection
)
from app.services.cookie_manager import CookieConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

def demo_bilibili_collections():
    """演示B站合集处理功能"""
    
    print("🎬 B站合集处理功能演示")
    print("=" * 50)
    
    # 初始化cookie管理器
    cookie_manager = CookieConfigManager()
    
    # 检查登录状态
    bilibili_cookie = cookie_manager.get("bilibili")
    if bilibili_cookie:
        print("✅ 已检测到B站登录cookie，可以访问需要登录的内容")
        print(f"🍪 Cookie预览: {bilibili_cookie[:50]}...")
    else:
        print("⚠️ 未检测到B站登录cookie，部分功能可能受限")
        print("💡 建议先通过前端页面扫码登录B站")
    
    print("\n" + "=" * 50)
    
    # 测试用例列表
    test_cases = [
        # 基础视频类型
        {
            "name": "单个视频（多分P）",
            "url": "https://www.bilibili.com/video/BV1BZ4y1u7zT",
            "description": "测试多分P视频的合集识别"
        },
        {
            "name": "UGC合集视频",
            "url": "https://www.bilibili.com/video/BV1234567890",  # 示例URL
            "description": "测试用户创建的视频合集"
        },
        
        # 明确的合集类型
        {
            "name": "收藏夹",
            "url": "https://space.bilibili.com/123456/favlist?fid=789012345",
            "description": "测试公开收藏夹"
        },
        {
            "name": "个人合集",
            "url": "https://space.bilibili.com/123456/channel/collectiondetail?sid=234567",
            "description": "测试UP主创建的合集"
        },
        {
            "name": "系列视频",
            "url": "https://space.bilibili.com/123456/channel/seriesdetail?sid=345678",
            "description": "测试系列视频"
        },
        {
            "name": "稍后再看",
            "url": "https://www.bilibili.com/watchlater",
            "description": "测试稍后再看列表（需要登录）"
        },
        
        # 番剧类型
        {
            "name": "番剧系列",
            "url": "https://www.bilibili.com/bangumi/play/ss12345",
            "description": "测试番剧系列"
        },
        {
            "name": "番剧媒体",
            "url": "https://www.bilibili.com/bangumi/media/md54321",
            "description": "测试番剧媒体页面"
        },
        
        # 其他平台对比
        {
            "name": "抖音视频",
            "url": "https://www.douyin.com/video/1234567890123456789",
            "description": "测试抖音平台识别"
        },
        {
            "name": "YouTube视频",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "description": "测试YouTube平台识别"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 测试用例 {i}: {test_case['name']}")
        print(f"🔗 URL: {test_case['url']}")
        print(f"📝 说明: {test_case['description']}")
        print("-" * 30)
        
        try:
            # 1. 识别平台
            platform = identify_platform(test_case['url'])
            print(f"🎯 平台识别: {platform or '未知平台'}")
            
            if not platform:
                print("❌ 无法识别平台，跳过")
                continue
            
            # 2. 检查是否为合集
            is_collection = is_collection_url(test_case['url'], platform)
            print(f"📚 是否为合集: {'是' if is_collection else '否'}")
            
            # 3. 如果是B站单视频，检查是否属于合集
            if platform == "bilibili" and not is_collection:
                is_part_of_collection = is_video_part_of_collection(test_case['url'])
                print(f"🔗 是否属于合集: {'是' if is_part_of_collection else '否'}")
                is_collection = is_part_of_collection
            
            # 4. 如果是合集，尝试提取视频列表
            if is_collection:
                print("🎬 开始提取合集视频...")
                videos = extract_collection_videos(test_case['url'], platform, max_videos=5)
                
                if videos:
                    print(f"✅ 成功提取 {len(videos)} 个视频:")
                    for j, (video_url, title) in enumerate(videos[:3], 1):
                        print(f"  {j}. {title}")
                        print(f"     {video_url}")
                    
                    if len(videos) > 3:
                        print(f"  ... 还有 {len(videos) - 3} 个视频")
                else:
                    print("❌ 未能提取到视频")
            else:
                print("ℹ️ 这是单个视频，不是合集")
                
        except Exception as e:
            print(f"❌ 处理出错: {e}")
            logger.error(f"测试用例 {i} 出错: {e}")
        
        print()

def demo_api_usage():
    """演示API使用方法"""
    
    print("\n🔧 API使用方法演示")
    print("=" * 50)
    
    print("""
1. 平台识别:
   from app.utils.url_parser import identify_platform
   platform = identify_platform(url)

2. 合集检测:
   from app.utils.url_parser import is_collection_url
   is_collection = is_collection_url(url, platform)

3. 单视频合集检测（仅B站）:
   from app.utils.url_parser import is_video_part_of_collection
   is_part = is_video_part_of_collection(url)

4. 提取合集视频:
   from app.utils.url_parser import extract_collection_videos
   videos = extract_collection_videos(url, platform, max_videos=50)

5. 登录状态管理:
   from app.services.cookie_manager import CookieConfigManager
   cookie_manager = CookieConfigManager()
   cookie = cookie_manager.get("bilibili")  # 获取
   cookie_manager.set("bilibili", cookie)   # 设置
   
支持的B站合集类型:
- 收藏夹 (favlist)
- 个人合集 (collectiondetail)  
- 系列视频 (seriesdetail)
- 稍后再看 (watchlater) - 需要登录
- 番剧系列 (bangumi/play/ss)
- 番剧媒体 (bangumi/media/md)
- 多分P视频
- UGC合集
- 用户投稿列表
    """)

def main():
    """主函数"""
    print("🚀 B站合集处理功能演示程序")
    print("基于 bilibili-API-collect 项目的API文档改进")
    
    # 运行演示
    demo_bilibili_collections()
    demo_api_usage()
    
    print("\n" + "=" * 50)
    print("✅ 演示完成!")
    print("💡 如需访问需要登录的内容，请先通过前端页面扫码登录B站")
    print("📚 参考文档: https://socialsisteryi.github.io/bilibili-API-collect/")

if __name__ == "__main__":
    main() 