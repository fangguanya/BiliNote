import re
from typing import Optional, List, Tuple
import yt_dlp
import requests
from urllib.parse import urlparse, parse_qs
import os

# 添加日志支持
from app.utils.logger import get_logger
from app.services.cookie_manager import CookieConfigManager
from app.utils.title_cleaner import smart_title_clean

logger = get_logger(__name__)

# 初始化Cookie管理器
cookie_manager = CookieConfigManager()

def extract_video_id(url: str, platform: str) -> Optional[str]:
    """
    从视频链接中提取视频 ID

    :param url: 视频链接
    :param platform: 平台名（bilibili / youtube / douyin / baidu_pan）
    :return: 提取到的视频 ID 或 None
    """
    if platform == "bilibili":
        # 匹配 BV号（如 BV1vc411b7Wa）
        match = re.search(r"BV([0-9A-Za-z]+)", url)
        return f"BV{match.group(1)}" if match else None

    elif platform == "youtube":
        # 匹配 v=xxxxx 或 youtu.be/xxxxx，ID 长度通常为 11
        match = re.search(r"(?:v=|youtu\.be/)([0-9A-Za-z_-]{11})", url)
        return match.group(1) if match else None

    elif platform == "douyin":
        # 匹配 douyin.com/video/1234567890123456789
        match = re.search(r"/video/(\d+)", url)
        return match.group(1) if match else None

    elif platform == "baidu_pan":
        # 百度网盘分享链接：https://pan.baidu.com/s/1ABC123DEF
        # 或目录链接：https://pan.baidu.com/disk/home#/path=/视频目录
        share_match = re.search(r"/s/([0-9A-Za-z_-]+)", url)
        if share_match:
            return share_match.group(1)
        
        # 目录路径提取
        path_match = re.search(r"#/path=([^&]+)", url)
        if path_match:
            return path_match.group(1)
        
        # 文件fsid提取（用于特定文件）
        fsid_match = re.search(r"fsid=(\d+)", url)
        if fsid_match:
            return fsid_match.group(1)
        
        return None

    return None


def is_video_part_of_collection(url: str) -> bool:
    """
    检查单个B站视频是否属于某个合集
    参考BilibiliDown项目的合集检测逻辑
    
    :param url: 视频链接
    :return: 是否属于合集
    """
    logger.info(f"🔍 检查视频是否属于合集: {url}")
    
    # 提取BV号
    bv_match = re.search(r"BV([0-9A-Za-z]+)", url)
    if not bv_match:
        logger.info("❌ 无法提取BV号")
        return False
    
    bv_id = f"BV{bv_match.group(1)}"
    logger.info(f"📹 提取到BV号: {bv_id}")
    
    # 使用B站API进行准确检测
    try:
        logger.info(f"🌐 使用B站API检查视频合集信息...")
        
        import requests
        
        # 使用B站视频信息API
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        }
        
        # 添加登录cookie支持
        bilibili_cookie = cookie_manager.get("bilibili")
        if bilibili_cookie:
            logger.info("🍪 使用已保存的B站登录cookie")
            headers['Cookie'] = bilibili_cookie
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('code') == 0 and 'data' in data:
                video_data = data['data']
                logger.info(f"📊 成功获取视频信息: {video_data.get('title', '未知标题')}")
                
                # 检查1: 是否属于UGC合集（ugc_season）
                if 'ugc_season' in video_data and video_data['ugc_season']:
                    season_info = video_data['ugc_season']
                    season_title = season_info.get('title', '未知合集')
                    logger.info(f"✅ 视频 {bv_id} 属于UGC合集: {season_title}")
                    return True
                
                # 检查2: 是否有多分P且数量较多（3个以上认为是合集）
                if 'pages' in video_data and len(video_data['pages']) > 2:
                    page_count = len(video_data['pages'])
                    logger.info(f"✅ 视频 {bv_id} 有 {page_count} 个分P，认为是合集")
                    return True
                
                # 检查3: 是否属于番剧/电影等（season字段）
                if 'season' in video_data and video_data['season']:
                    season_info = video_data['season']
                    season_title = season_info.get('title', '未知番剧')
                    logger.info(f"✅ 视频 {bv_id} 属于番剧: {season_title}")
                    return True
                
                # 检查4: 是否属于系列视频（通过up主的其他视频判断）
                if 'owner' in video_data:
                    owner_mid = video_data['owner'].get('mid')
                    video_title = video_data.get('title', '')
                    
                    # 如果标题包含明显的系列标识，也认为是合集
                    series_keywords = ['合集', '系列', '第一集', '第二集', 'P1', 'P2', '上篇', '下篇', '（一）', '（二）', 
                                     '【合集】', '【系列】', '全集', '连载', '番外', 'EP', 'ep']
                    if any(keyword in video_title for keyword in series_keywords):
                        logger.info(f"✅ 视频 {bv_id} 标题包含系列关键词，认为是合集")
                        return True
                
                # 检查5: 尝试检查是否有相关的合集信息
                # 使用视频详细信息API获取更多数据
                detail_api_url = f"https://api.bilibili.com/x/web-interface/view/detail?bvid={bv_id}"
                detail_headers = headers.copy()
                if bilibili_cookie:
                    detail_headers['Cookie'] = bilibili_cookie
                detail_response = requests.get(detail_api_url, headers=detail_headers, timeout=8)
                
                if detail_response.status_code == 200:
                    detail_data = detail_response.json()
                    if detail_data.get('code') == 0 and 'data' in detail_data:
                        detail_info = detail_data['data']
                        
                        # 检查是否有相关视频信息
                        if 'Related' in detail_info and len(detail_info['Related']) > 3:
                            logger.info(f"✅ 视频 {bv_id} 有较多相关视频，可能是系列内容")
                            return True
                            
        else:
            logger.warning(f"⚠️ B站API请求失败: {response.status_code}")
            
    except Exception as e:
        logger.warning(f"⚠️ B站API检查失败: {e}")
    
    # 如果所有检查都无法确定，保守地认为不是合集
    logger.info(f"❌ 视频 {bv_id} 通过多种方法检查后，无法确定是否属于合集，默认为单视频")
    return False


def is_collection_url(url: str, platform: str) -> bool:
    """
    检测是否为合集URL
    
    支持的合集类型：
    - B站：收藏夹、个人合集、系列视频、稍后再看、番剧系列、多分P视频、UGC合集、用户投稿、频道首页
    - 抖音：用户主页、话题页面
    - 百度网盘：目录、分享文件夹
    
    :param url: 视频链接  
    :param platform: 平台名
    :return: 是否为合集
    """
    logger.info(f"🔍 检测合集URL: {url} (平台: {platform})")
    
    if platform == "bilibili":
        # B站合集检测模式（已改进）
        collection_patterns = [
            r"favlist\?fid=",                    # 收藏夹
            r"collectiondetail\?sid=",           # 个人合集
            r"seriesdetail\?sid=",               # 系列视频  
            r"watchlater",                       # 稍后再看
            r"bangumi/play/ss\d+",               # 番剧系列
            r"bangumi/media/md\d+",              # 番剧媒体
            r"space\.bilibili\.com/\d+/video",   # 用户投稿页
            r"channel/index",                    # 频道首页
        ]
        
        for i, pattern in enumerate(collection_patterns):
            if re.search(pattern, url):
                pattern_names = ["收藏夹", "个人合集", "系列视频", "稍后再看", "番剧系列", "番剧媒体", "用户投稿", "频道首页"]
                logger.info(f"✅ 检测到B站{pattern_names[i]}链接: {pattern}")
                return True
        
        # 检查是否为多分P视频或属于合集的单视频
        if re.search(r"bilibili\.com/video/BV", url):
            logger.info("🔍 检测到B站视频，检查是否属于合集")
            # 调用详细的合集检测函数
            return is_video_part_of_collection(url)
        
        logger.info("❌ 不是B站合集链接")
        return False
    
    elif platform == "douyin":
        # 抖音合集检测模式（用户主页或话题页）
        collection_patterns = [
            r"douyin\.com/user/",  # 用户主页
            r"douyin\.com/hashtag/",  # 话题页面
        ]
        
        for i, pattern in enumerate(collection_patterns):
            if re.search(pattern, url):
                pattern_names = ["用户主页", "话题页面"]
                logger.info(f"✅ 检测到抖音{pattern_names[i]}链接: {pattern}")
                return True
        
        logger.info("❌ 不是抖音合集链接")
        return False
    
    elif platform == "baidu_pan":
        # 百度网盘合集检测模式
        collection_patterns = [
            r"#/path=/",                         # 目录路径
            r"/disk/home",                       # 个人网盘主页
            r"dir\?path=",                       # 目录参数
        ]
        
        for i, pattern in enumerate(collection_patterns):
            if re.search(pattern, url):
                pattern_names = ["目录路径", "网盘主页", "目录参数"]
                logger.info(f"✅ 检测到百度网盘{pattern_names[i]}链接: {pattern}")
                return True
        
        # 分享链接默认也可能包含多个文件
        if re.search(r"/s/[0-9A-Za-z_-]+", url):
            logger.info("✅ 检测到百度网盘分享链接，可能包含多个文件")
            return True
        
        logger.info("❌ 不是百度网盘合集链接")
        return False
    
    logger.info(f"❌ 不支持的平台: {platform}")
    return False


def extract_collection_videos(url: str, platform: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    提取合集中的所有视频
    
    :param url: 合集链接
    :param platform: 平台名
    :param max_videos: 最大视频数量
    :return: [(video_url, title), ...] 列表
    """
    logger.info(f"🎬 开始提取合集视频: {url} (平台: {platform}, 最大数量: {max_videos})")
    
    if platform == "bilibili":
        return _extract_bilibili_collection_videos(url, max_videos)
    elif platform == "douyin":
        return _extract_douyin_collection_videos(url, max_videos)
    elif platform == "baidu_pan":
        return extract_baidu_pan_collection_videos(url, max_videos)
    else:
        logger.warning(f"⚠️ 不支持的平台: {platform}")
        return []


def _extract_bilibili_collection_videos(url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    提取B站合集中的视频
    """
    logger.info(f"🔧 使用B站提取器处理: {url}")
    videos = []
    
    try:
        # 检查是否是单视频属于合集的情况
        video_pattern = r"bilibili\.com/video/[A-Za-z0-9]+"
        if re.search(video_pattern, url) and is_video_part_of_collection(url):
            logger.info("📺 单视频属于合集，尝试提取完整合集")
            # 如果是单视频属于合集，尝试通过yt-dlp获取完整合集
            return _extract_bilibili_video_collection_via_ytdlp(url, max_videos)
        
        # 使用yt-dlp提取播放列表信息（设置超时）
        logger.info("🔄 尝试使用yt-dlp提取播放列表...")
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # 只提取URL，不下载
            'socket_timeout': 10,  # 10秒网络超时
            'retries': 0,  # 不重试
            'fragment_retries': 0,  # 片段不重试
        }
        
        # 使用线程和超时控制
        import threading
        result = {"info": None, "error": None}
        
        def extract_playlist_thread():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    result["info"] = ydl.extract_info(url, download=False)
            except Exception as e:
                result["error"] = e
        
        # 启动线程
        thread = threading.Thread(target=extract_playlist_thread)
        thread.daemon = True
        thread.start()
        
        # 等待最多15秒
        thread.join(timeout=15)
        
        if thread.is_alive():
            logger.warning(f"⚠️ yt-dlp播放列表提取超时: {url}")
            # 尝试API方式
            return _extract_bilibili_collection_by_api(url, max_videos)
        
        if result["error"]:
            raise result["error"]
        
        info = result["info"]
        
        if info and 'entries' in info:
            # 这是一个播放列表
            logger.info(f"✅ yt-dlp检测到播放列表，包含 {len(info['entries'])} 个条目")
            for entry in info['entries'][:max_videos]:
                if entry.get('url') and entry.get('title'):
                    video_url = entry['url']
                    if not video_url.startswith('http'):
                        video_url = f"https://www.bilibili.com/video/{video_url}"
                    videos.append((video_url, entry['title']))
                    
            logger.info(f"✅ yt-dlp提取成功，获得 {len(videos)} 个视频")
        else:
            # 尝试通过API获取合集信息
            logger.info("⚠️ yt-dlp未检测到播放列表，尝试使用API方式...")
            videos = _extract_bilibili_collection_by_api(url, max_videos)
                
    except Exception as e:
        logger.error(f"❌ 提取B站合集视频失败: {e}")
        # 如果yt-dlp失败，尝试API方式作为备选
        try:
            logger.info("🔄 尝试使用API方式作为备选...")
            videos = _extract_bilibili_collection_by_api(url, max_videos)
        except Exception as api_e:
            logger.error(f"❌ API方式也失败: {api_e}")
        
    return videos


def _extract_bilibili_video_collection_via_ytdlp(url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    通过B站API从单个视频提取其所属合集的所有视频
    参考BilibiliDown项目的实现思路
    """
    logger.info(f"🔍 尝试从单视频提取完整合集: {url}")
    videos = []
    
    # 提取BV号
    bv_match = re.search(r"BV([0-9A-Za-z]+)", url)
    if not bv_match:
        logger.error("❌ 无法从URL提取BV号")
        return videos
    
    bv_id = f"BV{bv_match.group(1)}"
    logger.info(f"📹 提取到BV号: {bv_id}")
    
    try:
        # 使用B站API获取视频信息
        logger.info("🌐 通过B站API获取视频详细信息...")
        
        import requests
        
        # 获取视频基本信息
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        }
        
        # 添加登录cookie支持
        bilibili_cookie = cookie_manager.get("bilibili")
        if bilibili_cookie:
            logger.info("🍪 使用已保存的B站登录cookie获取合集信息")
            headers['Cookie'] = bilibili_cookie
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('code') == 0 and 'data' in data:
                video_data = data['data']
                video_title = video_data.get('title', '未知标题')
                logger.info(f"📊 获取到视频信息: {video_title}")
                                
                # 方法1: 处理番剧/电影合集（season字段）
                if 'season' in video_data and video_data['season']:
                    season_info = video_data['season']
                    season_id = season_info.get('season_id')
                    season_title = season_info.get('title', '未知番剧')
                    
                    logger.info(f"✅ 发现番剧合集: {season_title} (Season ID: {season_id})")
                    
                    # 获取番剧的所有剧集
                    bangumi_api_url = f"https://api.bilibili.com/pgc/web/season/section?season_id={season_id}"
                    bangumi_headers = headers.copy()
                    if bilibili_cookie:
                        bangumi_headers['Cookie'] = bilibili_cookie
                    bangumi_response = requests.get(bangumi_api_url, headers=bangumi_headers, timeout=10)
                    
                    if bangumi_response.status_code == 200:
                        bangumi_data = bangumi_response.json()
                        
                        if bangumi_data.get('code') == 0 and 'result' in bangumi_data:
                            result = bangumi_data['result']
                            # 处理正片和花絮等
                            sections = result.get('section', [])
                            if not sections and 'main_section' in result:
                                sections = [result['main_section']]
                            
                            for section in sections:
                                episodes = section.get('episodes', [])
                                logger.info(f"📹 番剧章节包含 {len(episodes)} 个剧集")
                                
                                for episode in episodes:
                                    if episode.get('bvid') and episode.get('long_title'):
                                        episode_url = f"https://www.bilibili.com/video/{episode['bvid']}"
                                        episode_title = f"{episode.get('title', '')} {episode.get('long_title', '')}"
                                        videos.append((episode_url, episode_title.strip()))
                                
                            if videos:
                                logger.info(f"✅ 成功提取番剧合集 {len(videos)} 个剧集")
                                return videos
                
                # 方法2: 处理多分P视频
                if 'pages' in video_data and len(video_data['pages']) > 1:
                    pages = video_data['pages']
                    logger.info(f"📹 发现多分P视频，共 {len(pages)} 个分P")
                    
                    base_title = video_data.get('title', '未知标题')
                    for page in pages:
                        if page.get('page') and page.get('part'):
                            # 构造分P视频的URL
                            page_url = f"https://www.bilibili.com/video/{bv_id}?p={page['page']}"
                            # 直接使用API返回的分P标题，不需要额外清理
                            # API的part字段已经是干净的分P标题（如："63.64.2-KMEANS工作流程P64"）
                            part_title = page['part']
                            
                            # 只做基本的字符串清理，去掉首尾空格
                            cleaned_title = part_title.strip()
                            
                            logger.debug(f"📺 P{page['page']}: '{cleaned_title}'")
                            videos.append((page_url, cleaned_title))
                    
                    logger.info(f"✅ 成功提取多分P视频 {len(videos)} 个分集")
                    return videos
                
                # 方法3: 尝试通过UP主的其他视频查找系列
                if 'owner' in video_data:
                    owner_mid = video_data['owner'].get('mid')
                    video_title = video_data.get('title', '')
                    
                    # 检查是否为系列视频
                    series_keywords = ['合集', '系列', '第一集', '第二集', 'P1', 'P2', '上篇', '下篇']
                    if any(keyword in video_title for keyword in series_keywords):
                        logger.info(f"🔍 检测到系列关键词，尝试获取UP主的相关视频...")
                        
                        # 获取UP主的投稿视频列表
                        up_videos_api = f"https://api.bilibili.com/x/space/arc/search?mid={owner_mid}&ps=20&tid=0&pn=1&keyword=&order=pubdate"
                        up_response = requests.get(up_videos_api, headers=headers, timeout=10)
                        
                        if up_response.status_code == 200:
                            up_data = up_response.json()
                            if up_data.get('code') == 0 and 'data' in up_data and 'list' in up_data['data']:
                                up_videos = up_data['data']['list']['vlist']
                                
                                # 查找标题相似的视频
                                base_keywords = set(video_title.split())
                                related_videos = []
                                
                                for up_video in up_videos[:max_videos]:
                                    up_title = up_video.get('title', '')
                                    up_keywords = set(up_title.split())
                                    
                                    # 计算标题相似度（简单的关键词匹配）
                                    similarity = len(base_keywords.intersection(up_keywords)) / len(base_keywords.union(up_keywords))
                                    
                                    if similarity > 0.3 or any(keyword in up_title for keyword in series_keywords):
                                        up_bvid = up_video.get('bvid')
                                        if up_bvid:
                                            # 🧹 清理UP主相关视频标题
                                            cleaned_up_title = smart_title_clean(up_title, platform="bilibili", preserve_episode=False)
                                            related_videos.append((f"https://www.bilibili.com/video/{up_bvid}", cleaned_up_title))
                                
                                if len(related_videos) > 1:
                                    logger.info(f"✅ 发现 {len(related_videos)} 个相关系列视频")
                                    videos.extend(related_videos[:max_videos])
                                    return videos
                
                
                # 方法4: 处理UGC合集
                if 'ugc_season' in video_data and video_data['ugc_season']:
                    season_info = video_data['ugc_season']
                    season_id = season_info.get('id')
                    season_title = season_info.get('title', '未知合集')
                    
                    logger.info(f"✅ 发现UGC-Season合集: {season_title} (ID: {season_id})")
                    
                    # 获取合集中的所有视频
                    if 'owner' in video_data:
                        owner_mid = video_data['owner'].get('mid', 0)
                        collection_api_url = f"https://api.bilibili.com/x/polymer/space/seasons_archives_list?mid={owner_mid}&season_id={season_id}&sort_reverse=false&page_num=1&page_size={max_videos}"
                        
                        collection_response = requests.get(collection_api_url, headers=headers, timeout=10)
                        
                        if collection_response.status_code == 200:
                            collection_data = collection_response.json()
                            
                            if collection_data.get('code') == 0 and 'data' in collection_data and 'archives' in collection_data['data']:
                                archives = collection_data['data']['archives']
                                logger.info(f"📹 UGC合集包含 {len(archives)} 个视频")
                                
                                for archive in archives:
                                    if archive.get('bvid') and archive.get('title'):
                                        video_url = f"https://www.bilibili.com/video/{archive['bvid']}"
                                        # 🧹 清理UGC合集标题
                                        cleaned_archive_title = smart_title_clean(archive['title'], platform="bilibili", preserve_episode=False)
                                        videos.append((video_url, cleaned_archive_title))
                                
                                logger.info(f"✅ 成功提取UGC合集 {len(videos)} 个视频")
                                return videos
                    
                    # 处理正片和花絮等
                    sections = season_info.get('sections', [])
                    if not sections and 'main_section' in season_info:
                        sections = [season_info['main_section']]
                    
                    for section in sections:
                        episodes = section.get('episodes', [])
                        logger.info(f"📹 番剧章节包含 {len(episodes)} 个剧集")
                        
                        for episode in episodes:
                            if episode.get('bvid') and episode.get('title'):
                                episode_url = f"https://www.bilibili.com/video/{episode['bvid']}"
                                original_episode_title = f"{episode.get('title', '')}"
                                # 🧹 清理番剧集数标题
                                cleaned_episode_title = smart_title_clean(original_episode_title, platform="bilibili", preserve_episode=False)
                                videos.append((episode_url, cleaned_episode_title.strip()))
                        
                    if videos:
                        logger.info(f"✅ 成功提取番剧合集 {len(videos)} 个剧集")
                        return videos
                    
                # 如果没有找到合集信息，至少返回当前视频
                logger.info("📺 未找到合集信息，返回单视频")
                videos.append((url, video_title))
                return videos
                        
        # 如果API方法失败，尝试yt-dlp方法（作为备选）
        logger.info("🔄 API方法未成功，尝试yt-dlp方法...")
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 10,
            'retries': 1,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info and isinstance(info, dict):
                # 如果有entries信息，直接使用
                if 'entries' in info and len(info['entries']) > 1:
                    logger.info(f"📹 yt-dlp发现合集包含 {len(info['entries'])} 个视频")
                    for entry in info['entries'][:max_videos]:
                        if entry.get('webpage_url') and entry.get('title'):
                            videos.append((entry['webpage_url'], entry['title']))
                    
                    logger.info(f"✅ yt-dlp成功提取 {len(videos)} 个合集视频")
                
                else:
                    # 如果没有找到合集信息，将当前视频作为单个结果返回
                    logger.info("📺 yt-dlp未找到合集信息，返回单视频")
                    if info.get('webpage_url') and info.get('title'):
                        videos.append((info['webpage_url'], info['title']))
                        
    except Exception as e:
        logger.error(f"❌ 提取合集视频失败: {e}")
        # 作为最后的备选，至少返回原视频
        try:
            videos.append((url, "未知标题"))
        except:
            pass
    
    logger.info(f"🎬 最终提取到 {len(videos)} 个视频")
    return videos


def _extract_bilibili_collection_by_api(url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    通过B站API提取合集视频
    """
    logger.info(f"🌐 使用B站API提取: {url}")
    videos = []
    
    try:
        # 解析不同类型的B站合集URL
        if "favlist" in url:
            # 收藏夹
            logger.info("📁 处理收藏夹链接...")
            fid_match = re.search(r"fid=(\d+)", url)
            if fid_match:
                fid = fid_match.group(1)
                logger.info(f"📂 收藏夹ID: {fid}")
                api_url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fid}&pn=1&ps={max_videos}"
                videos = _fetch_bilibili_favlist_videos(api_url)
            else:
                logger.error("❌ 无法从收藏夹URL中提取fid")
                
        elif "collectiondetail" in url:
            # 合集
            logger.info("📚 处理合集链接...")
            sid_match = re.search(r"sid=(\d+)", url)
            if sid_match:
                sid = sid_match.group(1)
                logger.info(f"📖 合集ID: {sid}")
                api_url = f"https://api.bilibili.com/x/polymer/space/seasons_archives_list?mid=0&season_id={sid}&sort_reverse=false&page_num=1&page_size={max_videos}"
                videos = _fetch_bilibili_collection_videos(api_url)
            else:
                logger.error("❌ 无法从合集URL中提取sid")
                
        elif "seriesdetail" in url:
            # 系列
            logger.info("📚 处理系列链接...")
            sid_match = re.search(r"sid=(\d+)", url)
            if sid_match:
                sid = sid_match.group(1)
                logger.info(f"📖 系列ID: {sid}")
                api_url = f"https://api.bilibili.com/x/polymer/space/seasons_archives_list?mid=0&season_id={sid}&sort_reverse=false&page_num=1&page_size={max_videos}"
                videos = _fetch_bilibili_collection_videos(api_url)
            else:
                logger.error("❌ 无法从系列URL中提取sid")
                
        elif "watchlater" in url:
            # 稍后再看
            logger.info("⏰ 处理稍后再看...")
            api_url = f"https://api.bilibili.com/x/v2/history/toview?ps={max_videos}&pn=1"
            videos = _fetch_bilibili_watchlater_videos(api_url)
            
        elif "bangumi/play/ss" in url:
            # 番剧系列
            logger.info("🎭 处理番剧系列...")
            ss_match = re.search(r"ss(\d+)", url)
            if ss_match:
                ss_id = ss_match.group(1)
                logger.info(f"🎭 番剧系列ID: {ss_id}")
                api_url = f"https://api.bilibili.com/pgc/web/season/section?season_id={ss_id}"
                videos = _fetch_bilibili_bangumi_videos(api_url)
            else:
                logger.error("❌ 无法从番剧URL中提取ss_id")
                
        elif "bangumi/media/md" in url:
            # 番剧媒体
            logger.info("🎭 处理番剧媒体...")
            md_match = re.search(r"md(\d+)", url)
            if md_match:
                md_id = md_match.group(1)
                logger.info(f"🎭 番剧媒体ID: {md_id}")
                # 先获取season_id，再获取剧集列表
                media_api_url = f"https://api.bilibili.com/pgc/review/user?media_id={md_id}"
                videos = _fetch_bilibili_bangumi_by_media_id(media_api_url, max_videos)
            else:
                logger.error("❌ 无法从番剧媒体URL中提取md_id")
        else:
            logger.warning("⚠️ 未识别的B站合集类型")
                
    except Exception as e:
        logger.error(f"❌ 通过API提取B站合集失败: {e}")
        
    return videos


def _fetch_bilibili_favlist_videos(api_url: str) -> List[Tuple[str, str]]:
    """
    获取B站收藏夹视频列表
    """
    logger.info(f"📡 请求收藏夹API: {api_url}")
    videos = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        }
        
        # 添加登录cookie支持，用于访问私人收藏夹
        bilibili_cookie = cookie_manager.get("bilibili")
        if bilibili_cookie:
            logger.info("🍪 使用已保存的B站登录cookie访问收藏夹")
            headers['Cookie'] = bilibili_cookie
        
        response = requests.get(api_url, headers=headers)
        logger.info(f"📡 API响应状态: {response.status_code}")
        
        data = response.json()
        logger.info(f"📊 API响应数据: code={data.get('code')}, message={data.get('message', 'N/A')}")
        
        if data.get('code') == 0 and 'data' in data and 'medias' in data['data']:
            medias = data['data']['medias']
            logger.info(f"📹 收藏夹包含 {len(medias)} 个视频")
            
            for media in medias:
                if media.get('bvid') and media.get('title'):
                    video_url = f"https://www.bilibili.com/video/{media['bvid']}"
                    videos.append((video_url, media['title']))
            
            logger.info(f"✅ 成功提取 {len(videos)} 个收藏夹视频")
        else:
            logger.error(f"❌ 收藏夹API返回错误: {data}")
                    
    except Exception as e:
        logger.error(f"❌ 获取B站收藏夹视频失败: {e}")
        
    return videos


def _fetch_bilibili_collection_videos(api_url: str) -> List[Tuple[str, str]]:
    """
    获取B站合集视频列表
    """
    logger.info(f"📡 请求合集API: {api_url}")
    videos = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        }
        
        # 添加登录cookie支持，用于访问需要权限的合集
        bilibili_cookie = cookie_manager.get("bilibili")
        if bilibili_cookie:
            logger.info("🍪 使用已保存的B站登录cookie访问合集")
            headers['Cookie'] = bilibili_cookie
        
        response = requests.get(api_url, headers=headers)
        logger.info(f"📡 API响应状态: {response.status_code}")
        
        data = response.json()
        logger.info(f"📊 API响应数据: code={data.get('code')}, message={data.get('message', 'N/A')}")
        
        if data.get('code') == 0 and 'data' in data and 'archives' in data['data']:
            archives = data['data']['archives']
            logger.info(f"📹 合集包含 {len(archives)} 个视频")
            
            for archive in archives:
                if archive.get('bvid') and archive.get('title'):
                    video_url = f"https://www.bilibili.com/video/{archive['bvid']}"
                    videos.append((video_url, archive['title']))
            
            logger.info(f"✅ 成功提取 {len(videos)} 个合集视频")
        else:
            logger.error(f"❌ 合集API返回错误: {data}")
                    
    except Exception as e:
        logger.error(f"❌ 获取B站合集视频失败: {e}")
        
    return videos


def _fetch_bilibili_watchlater_videos(api_url: str) -> List[Tuple[str, str]]:
    """
    获取B站稍后再看视频列表
    """
    logger.info(f"📡 请求稍后再看API: {api_url}")
    videos = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        }
        
        # 稍后再看需要登录cookie
        bilibili_cookie = cookie_manager.get("bilibili")
        if bilibili_cookie:
            logger.info("🍪 使用已保存的B站登录cookie访问稍后再看")
            headers['Cookie'] = bilibili_cookie
        else:
            logger.warning("⚠️ 稍后再看需要登录，但未找到有效cookie")
            return videos
        
        response = requests.get(api_url, headers=headers)
        logger.info(f"📡 API响应状态: {response.status_code}")
        
        data = response.json()
        logger.info(f"📊 API响应数据: code={data.get('code')}, message={data.get('message', 'N/A')}")
        
        if data.get('code') == 0 and 'data' in data and 'list' in data['data']:
            video_list = data['data']['list']
            logger.info(f"📹 稍后再看包含 {len(video_list)} 个视频")
            
            for video in video_list:
                if video.get('bvid') and video.get('title'):
                    video_url = f"https://www.bilibili.com/video/{video['bvid']}"
                    videos.append((video_url, video['title']))
            
            logger.info(f"✅ 成功提取 {len(videos)} 个稍后再看视频")
        else:
            logger.error(f"❌ 稍后再看API返回错误: {data}")
                    
    except Exception as e:
        logger.error(f"❌ 获取B站稍后再看视频失败: {e}")
        
    return videos


def _fetch_bilibili_bangumi_videos(api_url: str) -> List[Tuple[str, str]]:
    """
    获取B站番剧视频列表
    """
    logger.info(f"📡 请求番剧API: {api_url}")
    videos = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        }
        
        # 添加登录cookie支持（部分番剧需要大会员）
        bilibili_cookie = cookie_manager.get("bilibili")
        if bilibili_cookie:
            logger.info("🍪 使用已保存的B站登录cookie访问番剧")
            headers['Cookie'] = bilibili_cookie
        
        response = requests.get(api_url, headers=headers)
        logger.info(f"📡 API响应状态: {response.status_code}")
        
        data = response.json()
        logger.info(f"📊 API响应数据: code={data.get('code')}, message={data.get('message', 'N/A')}")
        
        if data.get('code') == 0 and 'result' in data:
            result = data['result']
            # 处理正片和花絮等
            sections = result.get('section', [])
            if not sections and 'main_section' in result:
                sections = [result['main_section']]
            
            for section in sections:
                episodes = section.get('episodes', [])
                logger.info(f"📹 番剧章节包含 {len(episodes)} 个剧集")
                
                for episode in episodes:
                    if episode.get('bvid') and episode.get('long_title'):
                        episode_url = f"https://www.bilibili.com/video/{episode['bvid']}"
                        episode_title = f"{episode.get('title', '')} {episode.get('long_title', '')}"
                        videos.append((episode_url, episode_title.strip()))
            
            logger.info(f"✅ 成功提取 {len(videos)} 个番剧剧集")
        else:
            logger.error(f"❌ 番剧API返回错误: {data}")
                    
    except Exception as e:
        logger.error(f"❌ 获取B站番剧视频失败: {e}")
        
    return videos


def _fetch_bilibili_bangumi_by_media_id(api_url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    通过媒体ID获取B站番剧视频列表
    """
    logger.info(f"📡 请求番剧媒体API: {api_url}")
    videos = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        }
        
        # 添加登录cookie支持
        bilibili_cookie = cookie_manager.get("bilibili")
        if bilibili_cookie:
            logger.info("🍪 使用已保存的B站登录cookie访问番剧媒体")
            headers['Cookie'] = bilibili_cookie
        
        response = requests.get(api_url, headers=headers)
        logger.info(f"📡 API响应状态: {response.status_code}")
        
        data = response.json()
        logger.info(f"📊 API响应数据: code={data.get('code')}")
        
        if data.get('code') == 0 and 'result' in data and 'media' in data['result']:
            media_info = data['result']['media']
            season_id = media_info.get('season_id')
            
            if season_id:
                logger.info(f"🎭 获取到番剧season_id: {season_id}")
                # 使用season_id获取剧集列表
                season_api_url = f"https://api.bilibili.com/pgc/web/season/section?season_id={season_id}"
                videos = _fetch_bilibili_bangumi_videos(season_api_url)
            else:
                logger.error("❌ 无法从番剧媒体信息中获取season_id")
        else:
            logger.error(f"❌ 番剧媒体API返回错误: {data}")
                    
    except Exception as e:
        logger.error(f"❌ 获取B站番剧媒体视频失败: {e}")
        
    return videos


def _extract_douyin_collection_videos(url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    提取抖音合集中的视频
    """
    logger.info(f"🎵 使用抖音提取器处理: {url}")
    videos = []
    
    try:
        # 抖音的合集提取比较复杂，这里提供一个基础实现
        # 实际使用中可能需要根据抖音的具体API调整
        
        if "user/" in url:
            # 用户主页视频
            logger.info("👤 处理抖音用户主页...")
            videos = _fetch_douyin_user_videos(url, max_videos)
                
        elif "hashtag/" in url:
            # 话题视频
            logger.info("🏷️ 处理抖音话题页面...")
            hashtag_match = re.search(r"hashtag/([^/?]+)", url)
            if hashtag_match:
                hashtag = hashtag_match.group(1)
                logger.info(f"🏷️ 话题标签: {hashtag}")
                videos = _fetch_douyin_hashtag_videos(hashtag, max_videos)
            else:
                logger.error("❌ 无法从话题URL中提取hashtag")
        else:
            logger.warning("⚠️ 未识别的抖音合集类型")
                
    except Exception as e:
        logger.error(f"❌ 提取抖音合集视频失败: {e}")
        
    return videos


def _fetch_douyin_user_videos(user_url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    获取抖音用户的视频列表
    """
    logger.info(f"👤 获取抖音用户视频: {user_url}")
    videos = []
    
    try:
        from app.downloaders.douyin_downloader import DouyinDownloader
        logger.info("🔧 初始化抖音下载器...")
        downloader = DouyinDownloader()
        videos = downloader.get_user_collection_videos(user_url, max_videos)
        logger.info(f"✅ 抖音下载器返回 {len(videos)} 个视频")
        
    except Exception as e:
        logger.error(f"❌ 获取抖音用户视频失败: {e}")
        
    return videos


def _fetch_douyin_hashtag_videos(hashtag: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    获取抖音话题的视频列表
    """
    logger.info(f"🏷️ 获取抖音话题视频: {hashtag}")
    videos = []
    
    try:
        # 话题视频获取比较复杂，暂时留作占位
        logger.warning(f"⚠️ 获取话题 {hashtag} 的视频列表（暂未实现）")
        
    except Exception as e:
        logger.error(f"❌ 获取抖音话题视频失败: {e}")
        
    return videos


def identify_platform(url: str) -> Optional[str]:
    """
    根据URL识别视频平台
    
    :param url: 视频链接
    :return: 平台名称 (bilibili/douyin/youtube/kuaishou/baidu_pan) 或 None
    """
    logger.info(f"🔍 识别平台: {url}")
    
    # B站
    if re.search(r"bilibili\.com|b23\.tv", url):
        logger.info("✅ 识别为B站平台")
        return "bilibili"
    
    # 抖音
    elif re.search(r"douyin\.com|iesdouyin\.com", url):
        logger.info("✅ 识别为抖音平台")
        return "douyin"
    
    # YouTube
    elif re.search(r"youtube\.com|youtu\.be", url):
        logger.info("✅ 识别为YouTube平台")
        return "youtube"
    
    # 快手
    elif re.search(r"kuaishou\.com", url):
        logger.info("✅ 识别为快手平台")
        return "kuaishou"
    
    # 百度网盘
    elif re.search(r"pan\.baidu\.com", url):
        logger.info("✅ 识别为百度网盘平台")
        return "baidu_pan"
    
    logger.warning(f"⚠️ 未识别的平台: {url}")
    return None


def extract_baidu_pan_collection_videos(url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    提取百度网盘目录中的所有媒体文件
    
    :param url: 百度网盘目录链接
    :param max_videos: 最大文件数量
    :return: [(file_url, filename), ...] 列表
    """
    logger.info(f"☁️ 开始提取百度网盘媒体文件: {url}")
    
    try:
        from app.downloaders.baidu_pan_downloader import BaiduPanDownloader
        
        downloader = BaiduPanDownloader()
        
        # 解析URL类型
        share_code, extract_code = downloader.parse_share_url(url)
        
        if share_code:
            logger.info(f"📎 检测到分享链接: {share_code}")
            file_list = downloader.get_file_list(share_code=share_code, extract_code=extract_code)
        else:
            # 个人网盘目录
            path = downloader.parse_path_url(url)
            logger.info(f"📁 检测到个人网盘路径: {path}")
            file_list = downloader.get_file_list(path=path)
        
        if not file_list:
            logger.warning("⚠️ 未找到任何文件")
            return []
        
        # 过滤媒体文件
        media_files = downloader.filter_media_files(file_list)
        
        if not media_files:
            logger.warning("⚠️ 未找到任何媒体文件")
            return []
        
        # 限制文件数量
        media_files = media_files[:max_videos]
        
        # 构造返回结果
        videos = []
        for file_info in media_files:
            filename = file_info.get('server_filename', '')
            fs_id = str(file_info.get('fs_id', ''))
            
            # 构造虚拟URL（用于任务识别）
            file_url = f"baidu_pan://file/{fs_id}?filename={filename}&source_url={url}"
            title = os.path.splitext(filename)[0]  # 去掉扩展名作为标题
            
            videos.append((file_url, title))
            logger.info(f"📄 找到媒体文件: {title}")
        
        logger.info(f"✅ 百度网盘媒体文件提取完成，共 {len(videos)} 个文件")
        return videos
        
    except Exception as e:
        logger.error(f"❌ 提取百度网盘媒体文件失败: {e}")
        return []
