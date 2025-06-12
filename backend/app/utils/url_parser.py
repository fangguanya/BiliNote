import re
import os
import time
import json
import asyncio
from enum import Enum
from typing import List, Tuple, Optional, Dict, Union, Any
from functools import partial
import urllib.parse
from urllib.parse import urlparse, parse_qs
import requests
import yt_dlp
from app.utils.logger import get_logger
from app.utils.title_cleaner import smart_title_clean
from app.services.cookie_manager import CookieConfigManager

logger = get_logger(__name__)
cookie_manager = CookieConfigManager()


def extract_video_id(url: str, platform: str) -> Optional[str]:
    """
    从URL中提取视频ID
    """
    logger.info(f"提取视频ID: {url} (平台: {platform})")
    
    if platform == "bilibili":
        # BV开头的BV号: https://www.bilibili.com/video/BV1Ga411X7PT
        bv_match = re.search(r"(?:\/|^)(BV[a-zA-Z0-9]+)", url)
        if bv_match:
            return bv_match.group(1)
        
        # AV开头的AV号: https://www.bilibili.com/video/av13587499
        av_match = re.search(r"\/av(\d+)", url)
        if av_match:
            return "av" + av_match.group(1)
        
    elif platform == "douyin":
        # 标准链接: https://www.douyin.com/video/7152743691239720223
        video_match = re.search(r"\/video\/(\d+)", url)
        if video_match:
            return video_match.group(1)
        
        # 短链接形式，需要处理跳转
        if "v.douyin.com" in url:
            try:
                response = requests.head(url, allow_redirects=True, timeout=5)
                redirect_url = response.url
                logger.info(f"抖音短链接重定向到: {redirect_url}")
                return extract_video_id(redirect_url, platform)
            except Exception as e:
                logger.error(f"处理抖音短链接失败: {e}")
                
    elif platform == "local":
        # 本地文件路径，直接返回文件名
        file_name = os.path.basename(url)
        name_without_ext = os.path.splitext(file_name)[0]
        return name_without_ext
        
    elif platform == "baidu_pan":
        # 百度网盘链接可能直接使用文件名
        # 解析URL，尝试获取文件路径
        if "path=" in url:
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            if "path" in query_params:
                path = query_params["path"][0]
                # 使用路径的最后部分作为ID
                return os.path.basename(path)
        
        # 如果无法提取路径，使用当前时间戳
        return f"baidupan_{int(time.time())}"
        
    # 其他平台或未能识别时，返回None
    logger.warning(f"无法从URL提取视频ID: {url} (平台: {platform})")
    return None


def is_video_part_of_collection(url: str) -> bool:
    """
    判断视频是否是合集的一部分
    主要检查URL中的参数 (p= 或 vd_source=)
    """
    # B站标记:
    # - p=N (表示第N个视频)
    if "bilibili.com" in url and "p=" in url:
        return True
    
    # B站合集来源标记:
    # - from_spmid=
    # - vd_source=
    if "bilibili.com" in url and ("vd_source=" in url or "from_spmid=" in url):
        # 提取vd_source参数
        match = re.search(r"vd_source=([^&]+)", url)
        if match:
            vd_source = urllib.parse.unquote(match.group(1))
            # vd_source通常格式: xxxx_collection_xxxx 或 xxxx_series_xxxx
            return "collection" in vd_source or "series" in vd_source
            
    # 抖音合集标记:
    # - previous_page=particular_collection
    if "douyin.com" in url and "previous_page=particular_collection" in url:
        return True
    
    # 默认不是合集
    return False


def is_collection_url(url: str, platform: str) -> bool:
    """
    判断URL是否是一个合集链接
    返回True如果是合集链接，否则返回False
    """
    logger.info(f"检查是否为合集URL: {url} (平台: {platform})")
    
    if platform == "bilibili":
        # B站合集链接模式
        # 1. 收藏夹: https://space.bilibili.com/xxx/favlist?fid=xxx
        if "space.bilibili.com" in url and ("favlist" in url or "fav" in url):
            return True
            
        # 2. 专栏合集: https://space.bilibili.com/xxx/channel/seriesdetail?sid=xxx
        # 3. 视频合集: https://space.bilibili.com/xxx/channel/collectiondetail?sid=xxx
        if "space.bilibili.com" in url and ("seriesdetail" in url or "collectiondetail" in url):
            return True
            
        # 4. 稍后再看: https://www.bilibili.com/watchlater/#/list
        if "bilibili.com/watchlater" in url:
            return True
            
        # 5. 番剧系列: https://www.bilibili.com/bangumi/play/ss123
        if "bilibili.com/bangumi/play/ss" in url:
            return True
            
        # 6. 番剧媒体信息: https://www.bilibili.com/bangumi/media/md123
        if "bilibili.com/bangumi/media/md" in url:
            return True
    
    elif platform == "douyin":
        # 抖音用户的作品合集
        # https://www.douyin.com/user/MS4wLjABAAAATxxKmkv35HFMq3dXVBgZ1VR4ND3fq_hsPBqZBvz1LZo
        # 抖音合集页
        # https://www.douyin.com/collection/7123456789
        if "douyin.com/user" in url or "douyin.com/collection" in url:
            return True
    
    elif platform == "baidu_pan":
        # 百度网盘分享链接
        # https://pan.baidu.com/s/xxx
        # https://pan.baidu.com/share/init?surl=xxx
        # https://pan.baidu.com/disk/main#/directory/path=%2F[目录名称]
        if "pan.baidu.com" in url and ("/s/" in url or "surl=" in url or "main#/directory" in url):
            return True
    
    # 默认不是合集
    return False


def extract_collection_videos(url: str, platform: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    提取合集中的所有视频URL和标题
    返回一个(url, title)的列表
    为兼容性提供的同步接口
    """
    logger.info(f"🚀 [同步接口] 开始提取合集视频: {url} (平台: {platform})")
    
    if platform == "baidu_pan":
        # 百度网盘需要特殊处理，暂不支持异步
        return extract_baidu_pan_collection_videos(url, max_videos)
    
    # 其他平台统一用异步方法处理
    try:
        # 获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                 # 如果在Jupyter或类似环境中，这个方法可能有效
                task = loop.create_task(extract_collection_videos_async(url, platform, max_videos))
                # 注意：这种方式在某些场景下可能不会按预期工作，因为它没有阻塞等待结果
                # 但在FastAPI的同步路由中，这是个大问题。正确的做法是路由本身就该是async的。
                logger.warning("  - 在已运行的循环中创建任务，但无法同步等待结果。返回空列表。")
                return []
            else:
                return loop.run_until_complete(extract_collection_videos_async(url, platform, max_videos))
        except Exception as e:
            logger.error(f"❌ [同步接口] 在现有循环中运行失败: {e}", exc_info=True)
            return []
    except Exception as e:
        logger.error(f"❌ [同步接口] 提取失败: {e}", exc_info=True)
        return []


async def extract_collection_videos_async(url: str, platform: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    异步提取合集中的所有视频URL和标题
    """
    logger.info(f"🚀 [异步接口] 开始提取合集视频: {url} (平台: {platform})")
    
    try:
        if platform == "bilibili":
            return await _extract_bilibili_collection_videos_async(url, max_videos)
        elif platform == "douyin":
            # 抖音功能暂未完全异步化
            logger.warning("⚠️ 抖音合集提取暂未完全异步化")
            return []
        elif platform == "baidu_pan":
             # 百度网盘功能暂未完全异步化
            logger.warning("⚠️ 百度网盘合集提取暂未完全异步化")
            return []
        else:
            logger.warning(f"⚠️ 不支持的合集平台: {platform}")
            return []
                
    except Exception as e:
        logger.error(f"❌ 提取合集视频失败: {e}", exc_info=True)
        return []


async def _extract_bilibili_collection_videos_async(url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    B站合集提取核心逻辑（异步）
    """
    logger.info(f" B站合集提取核心逻辑 (异步): {url}")
    
    try:
        logger.info("  - 尝试使用 yt-dlp 提取 (异步)...")
        videos = await _extract_bilibili_video_collection_via_ytdlp_async(url, max_videos)
        if videos:
            logger.info(f"✅ yt-dlp 提取成功，共 {len(videos)} 个视频")
            return videos
        else:
            logger.info("  - yt-dlp 提取失败或无结果，尝试备用API方法")
    except Exception as e:
        logger.warning(f"⚠️ yt-dlp 提取失败: {e}，尝试备用API方法")

    try:
        logger.info("  - 尝试使用 B站API 提取 (异步)...")
        videos = await _extract_bilibili_collection_by_api_async(url, max_videos)
        if videos:
            logger.info(f"✅ B站API 提取成功，共 {len(videos)} 个视频")
            return videos
        else:
            logger.info("  - B站API 提取失败或无结果")
            return []
    except Exception as e:
        logger.error(f"❌ B站API 提取也失败: {e}", exc_info=True)
        return []

async def _extract_bilibili_video_collection_via_ytdlp_async(url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    使用 yt-dlp 异步提取B站合集视频
    """
    logger.info(f"  - [yt-dlp-async] 正在处理: {url}")
    loop = asyncio.get_running_loop()
    ydl_opts = {
        'quiet': True, 'extract_flat': 'in_playlist', 'playlistend': max_videos,
        'logger': logger, 'skip_download': True, 'ignoreerrors': True,
        'bilibili_api': 'web', 'format': 'bestvideo', 'socket_timeout': 15
    }
    bilibili_cookie = cookie_manager.get("bilibili")
    if bilibili_cookie:
        logger.info("  - [yt-dlp-async] 使用已保存的B站登录cookie")
        ydl_opts['cookiefile'] = cookie_manager.get_cookie_file_path("bilibili")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            extract_func = partial(ydl.extract_info, url, download=False)
            info_dict = await loop.run_in_executor(None, extract_func)
        videos = []
        if info_dict and 'entries' in info_dict:
            for entry in info_dict.get('entries', []):
                if entry and entry.get('url') and entry.get('title'):
                    videos.append((entry['url'], smart_title_clean(entry['title'])))
        return videos
    except Exception as e:
        logger.warning(f"  - [yt-dlp-async] 异步提取线程出错: {e}", exc_info=True)
        return []

async def _async_get_request(url: str, headers: dict, timeout: int = 10):
    """异步执行 requests.get"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(requests.get, url, headers=headers, timeout=timeout)
    )

async def _extract_bilibili_collection_by_api_async(url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    logger.info(f"🌐 [API-async] 使用B站API提取: {url}")
    if "favlist" in url:
        fid_match = re.search(r"fid=(\d+)", url)
        if fid_match:
            api_url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fid_match.group(1)}&pn=1&ps={max_videos}"
            return await _fetch_bilibili_favlist_videos_async(api_url)
    elif "collectiondetail" in url or "seriesdetail" in url:
        sid_match = re.search(r"sid=(\d+)", url)
        if sid_match:
            api_url = f"https://api.bilibili.com/x/polymer/space/seasons_archives_list?mid=0&season_id={sid_match.group(1)}&sort_reverse=false&page_num=1&page_size={max_videos}"
            return await _fetch_bilibili_collection_videos_async(api_url)
    elif "watchlater" in url:
        api_url = f"https://api.bilibili.com/x/v2/history/toview?ps={max_videos}&pn=1"
        return await _fetch_bilibili_watchlater_videos_async(api_url)
    elif "bangumi/play/ss" in url:
        ss_match = re.search(r"ss(\d+)", url)
        if ss_match:
            api_url = f"https://api.bilibili.com/pgc/web/season/section?season_id={ss_match.group(1)}"
            return await _fetch_bilibili_bangumi_videos_async(api_url)
    elif "bangumi/media/md" in url:
        md_match = re.search(r"md(\d+)", url)
        if md_match:
            media_api_url = f"https://api.bilibili.com/pgc/review/user?media_id={md_match.group(1)}"
            return await _fetch_bilibili_bangumi_by_media_id_async(media_api_url, max_videos)
    logger.warning("⚠️ [API-async] 未识别的B站合集类型")
    return []

async def _fetch_bilibili_favlist_videos_async(api_url: str) -> List[Tuple[str, str]]:
    logger.info(f"📡 [API-async] 请求收藏夹API: {api_url}")
    headers = {'User-Agent': 'Mozilla/5.0...', 'Referer': 'https://www.bilibili.com/'}
    if cookie := cookie_manager.get("bilibili"): headers['Cookie'] = cookie
    try:
        response = await _async_get_request(api_url, headers)
        data = response.json()
        if data.get('code') == 0 and data.get('data', {}).get('medias'):
            return [(f"https://www.bilibili.com/video/{m['bvid']}", m['title']) for m in data['data']['medias'] if m.get('bvid') and m.get('title')]
    except Exception as e:
        logger.error(f"❌ [API-async] 获取收藏夹失败: {e}")
    return []

async def _fetch_bilibili_collection_videos_async(api_url: str) -> List[Tuple[str, str]]:
    logger.info(f"📡 [API-async] 请求合集API: {api_url}")
    headers = {'User-Agent': 'Mozilla/5.0...', 'Referer': 'https://www.bilibili.com/'}
    if cookie := cookie_manager.get("bilibili"): headers['Cookie'] = cookie
    try:
        response = await _async_get_request(api_url, headers)
        data = response.json()
        if data.get('code') == 0 and data.get('data', {}).get('archives'):
            return [(f"https://www.bilibili.com/video/{a['bvid']}", a['title']) for a in data['data']['archives'] if a.get('bvid') and a.get('title')]
    except Exception as e:
        logger.error(f"❌ [API-async] 获取合集视频失败: {e}")
    return []

async def _fetch_bilibili_watchlater_videos_async(api_url: str) -> List[Tuple[str, str]]:
    logger.info(f"📡 [API-async] 请求稍后再看API: {api_url}")
    headers = {'User-Agent': 'Mozilla/5.0...', 'Referer': 'https://www.bilibili.com/'}
    if not (cookie := cookie_manager.get("bilibili")):
        logger.warning("⚠️ [API-async] 稍后再看需要登录cookie")
        return []
    headers['Cookie'] = cookie
    try:
        response = await _async_get_request(api_url, headers)
        data = response.json()
        if data.get('code') == 0 and data.get('data', {}).get('list'):
            return [(f"https://www.bilibili.com/video/{v['bvid']}", v['title']) for v in data['data']['list'] if v.get('bvid') and v.get('title')]
    except Exception as e:
        logger.error(f"❌ [API-async] 获取稍后再看失败: {e}")
    return []

async def _fetch_bilibili_bangumi_videos_async(api_url: str) -> List[Tuple[str, str]]:
    logger.info(f"📡 [API-async] 请求番剧API: {api_url}")
    headers = {'User-Agent': 'Mozilla/5.0...', 'Referer': 'https://www.bilibili.com/'}
    if cookie := cookie_manager.get("bilibili"): headers['Cookie'] = cookie
    try:
        response = await _async_get_request(api_url, headers)
        data = response.json()
        videos = []
        if data.get('code') == 0 and 'result' in data:
            sections = data['result'].get('section', [])
            if not sections and 'main_section' in data['result']: sections = [data['result']['main_section']]
            for section in sections:
                for ep in section.get('episodes', []):
                    if ep.get('bvid') and ep.get('long_title'):
                        title = f"{ep.get('title', '')} {ep.get('long_title', '')}".strip()
                        videos.append((f"https://www.bilibili.com/video/{ep['bvid']}", title))
        return videos
    except Exception as e:
        logger.error(f"❌ [API-async] 获取番剧失败: {e}")
    return []

async def _fetch_bilibili_bangumi_by_media_id_async(api_url: str, max_videos: int) -> List[Tuple[str, str]]:
    logger.info(f"📡 [API-async] 请求番剧媒体API: {api_url}")
    headers = {'User-Agent': 'Mozilla/5.0...', 'Referer': 'https://www.bilibili.com/'}
    if cookie := cookie_manager.get("bilibili"): headers['Cookie'] = cookie
    try:
        response = await _async_get_request(api_url, headers)
        data = response.json()
        if data.get('code') == 0 and data.get('result', {}).get('media', {}).get('season_id'):
            season_id = data['result']['media']['season_id']
            # 有了season_id，就能拿到番剧详情
            season_api = f"https://api.bilibili.com/pgc/web/season/section?season_id={season_id}"
            return await _fetch_bilibili_bangumi_videos_async(season_api)
    except Exception as e:
        logger.error(f"❌ [API-async] 获取番剧媒体信息失败: {e}")
    return []


def identify_platform(url: str) -> Optional[str]:
    """
    识别URL属于哪个平台
    返回平台标识符（bilibili, douyin等）或None表示无法识别
    """
    # 处理本地文件
    if not url.startswith(("http://", "https://")):
        if os.path.exists(url) or url.startswith(("file://", "/", "C:\\", "D:\\")):
            return "local"
    
    # 处理各大视频平台
    if "bilibili.com" in url:
        return "bilibili"
    elif "douyin.com" in url or "iesdouyin.com" in url:
        return "douyin"
    elif "pan.baidu.com" in url:
        return "baidu_pan"
    
    # 不支持的平台
    return None


def extract_baidu_pan_collection_videos(url: str, max_videos: int = 50) -> List[Tuple[str, str]]:
    """
    提取百度网盘分享链接中的视频文件
    返回文件列表(url, title)
    
    百度网盘处理比较特殊，需要经过身份验证，此处简单实现
    实际应用中需要处理身份验证、提取码等
    """
    logger.info(f"🌐 [百度网盘] 处理网盘链接: {url}")
    
    # 这里实际上应该返回真实的文件列表
    # 但由于百度网盘的API访问需要复杂的身份验证和授权
    # 这里只是返回一个空列表，实际业务应该由百度网盘API专门模块处理
    
    from app.services.baidu_pan import BaiduPanService
    
    try:
        # 通过服务获取文件列表
        baidu_service = BaiduPanService()
        if "share/init" in url or "/s/" in url:
            logger.info("检测到百度网盘分享链接")
            
            # 提取分享码
            share_code = None
            if "/s/" in url:
                share_code = url.split("/s/")[1].split("?")[0]
            elif "surl=" in url:
                share_code = re.search(r"surl=([^&]+)", url).group(1)
                
            # 提取提取码
            extract_code = None
            if "?pwd=" in url:
                extract_code = url.split("?pwd=")[1].split("&")[0]
                
            logger.info(f"分享码: {share_code}, 提取码: {extract_code}")
            
            # 获取分享链接中的文件列表
            files = baidu_service.list_shared_files(share_code, extract_code)
            if files:
                # 过滤视频文件
                video_files = [(f"{share_code}|{f['fs_id']}|{f['path']}", f['server_filename']) 
                              for f in files if f.get('category') == 1]  # 1表示视频
                return video_files[:max_videos]
        else:
            # 个人网盘目录
            if "path=" in url:
                path = urllib.parse.unquote(re.search(r"path=([^&]+)", url).group(1))
                logger.info(f"百度网盘目录: {path}")
                
                # 获取个人网盘中的文件列表
                files = baidu_service.list_files(path)
                if files:
                    # 过滤视频文件
                    video_files = [(f"personal|{f['fs_id']}|{f['path']}", f['server_filename']) 
                                  for f in files if f.get('category') == 1]  # 1表示视频
                    return video_files[:max_videos]
                
    except Exception as e:
        logger.error(f"❌ 获取百度网盘文件失败: {e}", exc_info=True)
        
    # 若无法获取真实文件，返回空列表
    return []
