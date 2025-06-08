import datetime
import json
import os
import re
from typing import Union, Optional, List, Tuple
from urllib.parse import quote, urlencode

import httpx
import requests
from pydantic import BaseModel

from app.downloaders.base import Downloader
from app.downloaders.douyin_helper.abogus import ABogus
from app.enmus.note_enums import DownloadQuality
from app.models.audio_model import AudioDownloadResult
from app.services.cookie_manager import CookieConfigManager
from app.utils.path_helper import get_data_dir
from app.exceptions.auth_exceptions import AuthRequiredException
from app.utils.logger import get_logger
from dotenv import load_dotenv
from app.utils.title_cleaner import smart_title_clean

logger = get_logger(__name__)
load_dotenv()
DOUYIN_DOMAIN = "https://www.douyin.com"

cfm=CookieConfigManager()
def get_timestamp(unit: str = "milli"):
    """
    根据给定的单位获取当前时间 (Get the current time based on the given unit)

    Args:
        unit (str): 时间单位，可以是 "milli"、"sec"、"min" 等
            (The time unit, which can be "milli", "sec", "min", etc.)

    Returns:
        int: 根据给定单位的当前时间 (The current time based on the given unit)
    """

    now = datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)
    if unit == "milli":
        return int(now.total_seconds() * 1000)
    elif unit == "sec":
        return int(now.total_seconds())
    elif unit == "min":
        return int(now.total_seconds() / 60)
    else:
        raise ValueError("Unsupported time unit")


class DouyinConfig:
    HEADERS = {
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
        "Referer": "https://www.douyin.com/",
        "Cookie": None
    }

    PROXIES = {
        "http": None,
        "https": None,
    }

    MS_TOKEN = {
        "url": "https://mssdk.bytedance.com/web/report",
        "magic": 538969122,
        "version": 1,
        "dataType": 8,
        "strData": "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",
        "User-Agent": "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.47"
    }

    TTWID = {
        "url": "https://ttwid.bytedance.com/ttwid/union/register/",
        "data": '{"region":"cn","aid":1768,"needFid":false,"service":"www.ixigua.com","migrate_info":{"ticket":"","source":"node"},"cbUrlProtocol":"https","union":true}'
    }


class BaseRequestModel(BaseModel):
    device_platform: str = "webapp"
    aid: str = "6383"
    channel: str = "channel_pc_web"
    pc_client_type: int = 1
    version_code: str = "290100"
    version_name: str = "29.1.0"
    cookie_enabled: str = "true"
    screen_width: int = 1920
    screen_height: int = 1080
    browser_language: str = "zh-CN"
    browser_platform: str = "Win32"
    browser_name: str = "Chrome"
    browser_version: str = "130.0.0.0"
    browser_online: str = "true"
    engine_name: str = "Blink"
    engine_version: str = "130.0.0.0"
    os_name: str = "Windows"
    os_version: str = "10"
    cpu_core_num: int = 12
    device_memory: int = 8
    platform: str = "PC"
    downlink: str = "10"
    effective_type: str = "4g"
    from_user_page: str = "1"
    locate_query: str = "false"
    need_time_list: str = "1"
    pc_libra_divert: str = "Windows"
    publish_video_strategy_type: str = "2"
    round_trip_time: str = "0"
    show_live_replay_strategy: str = "1"
    time_list_query: str = "0"
    whale_cut_token: str = ""
    update_version_code: str = "170400"
    msToken: str = None


class DouyinDownloader(Downloader):
    def __init__(self, cookie=None):
        super().__init__()
        self.headers_config = DouyinConfig.HEADERS.copy()
        self.headers_config["Cookie"] = cfm.get('douyin')
        print(self.headers_config)
        self.proxies_config = DouyinConfig.PROXIES.copy()
        self.ttwid_config = DouyinConfig.TTWID.copy()
        self.ms_token_config = DouyinConfig.MS_TOKEN.copy()

    @staticmethod
    def find_url(string: str) -> list:
        url = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', string)
        return url

    def extract_video_id(self, url: str) -> str:
        video_url = self.find_url(url)

        if len(video_url):
            video_url = video_url[0]
            try:
                response = requests.head(video_url, allow_redirects=True)
                url = response.url
            except Exception as e:
                return ""
        patterns = [
            r'video/(\d+)',
            r'aweme_id=(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""

    def extract_user_sec_id(self, url: str) -> str:
        """从抖音用户主页URL中提取sec_user_id"""
        try:
            # 先访问URL获取重定向后的地址
            response = requests.head(url, allow_redirects=True, headers=self.headers_config)
            final_url = response.url
            
            # 从最终URL中提取sec_user_id
            patterns = [
                r'user/([^/?]+)',
                r'sec_user_id=([^&]+)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, final_url)
                if match:
                    return match.group(1)
                    
        except Exception as e:
            print(f"提取用户ID失败: {e}")
            
        return ""

    def gen_real_msToken(self) -> str:
        return DouyinConfig.MS_TOKEN.get("msToken", "")

    def _check_auth_required(self, error_message: str) -> bool:
        """检查错误信息是否表示需要认证"""
        auth_keywords = [
            "需要登录",
            "登录",
            "cookie", 
            "authentication",
            "请先登录",
            "未登录",
            "授权",
            "认证失败"
        ]
        
        error_lower = error_message.lower()
        return any(keyword in error_lower for keyword in auth_keywords)

    def fetch_video_info(self, video_url: str) -> json:
        aweme_id = self.extract_video_id(video_url)
        kwargs = self.headers_config
        print("kwargs:", kwargs)
        base_params = BaseRequestModel().model_dump()
        base_params["msToken"] = self.gen_real_msToken()
        base_params["aweme_id"] = aweme_id
        bogus = ABogus()
        ab_value = bogus.get_value(base_params)
        a_bogus = quote(ab_value, safe='')
        print(base_params)
        query_str = urlencode(base_params)
        full_url = f"{DOUYIN_DOMAIN}/aweme/v1/web/aweme/detail/?{query_str}&a_bogus={a_bogus}"

        print("Request URL:", full_url)

        try:
            response = requests.get(full_url, headers=kwargs)

            print("Response JSON:", response.content)
            return response.json()
        except Exception as e:
            print("请求失败:", e)
            if self._check_auth_required(str(e)):
                raise AuthRequiredException(
                    platform="douyin",
                    message="该视频需要抖音登录认证，请先扫码登录"
                )
            raise ValueError("请求失败:", e)
        # print(kwargs)

    def fetch_user_videos(self, sec_user_id: str, max_cursor: int = 0, count: int = 20) -> List[Tuple[str, str]]:
        """
        获取用户的视频列表
        
        :param sec_user_id: 用户的sec_user_id
        :param max_cursor: 分页游标
        :param count: 每页数量
        :return: [(video_url, title), ...] 列表
        """
        videos = []
        
        try:
            kwargs = self.headers_config
            base_params = BaseRequestModel().model_dump()
            base_params.update({
                "sec_user_id": sec_user_id,
                "max_cursor": max_cursor,
                "count": count,
                "msToken": self.gen_real_msToken()
            })
            
            bogus = ABogus()
            ab_value = bogus.get_value(base_params)
            a_bogus = quote(ab_value, safe='')
            query_str = urlencode(base_params)
            full_url = f"{DOUYIN_DOMAIN}/aweme/v1/web/aweme/post/?{query_str}&a_bogus={a_bogus}"
            
            print(f"获取用户视频列表: {full_url}")
            
            response = requests.get(full_url, headers=kwargs)
            data = response.json()
            
            if data.get('status_code') == 0 and 'aweme_list' in data:
                for aweme in data['aweme_list']:
                    if aweme.get('aweme_id') and aweme.get('desc'):
                        video_url = f"https://www.douyin.com/video/{aweme['aweme_id']}"
                        title = aweme['desc']
                        videos.append((video_url, title))
                        
                        if len(videos) >= count:
                            break
            
        except Exception as e:
            print(f"获取用户视频失败: {e}")
            
        return videos

    def get_user_collection_videos(self, user_url: str, max_videos: int = 20) -> List[Tuple[str, str]]:
        """
        从用户主页获取视频合集
        
        :param user_url: 用户主页URL
        :param max_videos: 最大获取数量
        :return: [(video_url, title), ...] 列表
        """
        videos = []
        
        try:
            sec_user_id = self.extract_user_sec_id(user_url)
            if not sec_user_id:
                print("无法提取用户ID")
                return videos
                
            print(f"提取到用户ID: {sec_user_id}")
            
            # 分页获取视频
            max_cursor = 0
            page_size = min(20, max_videos)  # 每页最多20个
            
            while len(videos) < max_videos:
                current_page_videos = self.fetch_user_videos(
                    sec_user_id=sec_user_id,
                    max_cursor=max_cursor,
                    count=page_size
                )
                
                if not current_page_videos:
                    break  # 没有更多视频了
                    
                videos.extend(current_page_videos)
                max_cursor += len(current_page_videos)
                
                # 如果当前页视频数量小于请求数量，说明已经到最后一页
                if len(current_page_videos) < page_size:
                    break
                    
        except Exception as e:
            print(f"获取用户合集视频失败: {e}")
            
        return videos[:max_videos]  # 确保不超过最大数量

    def download(
            self,
            video_url: str,
            output_dir: Union[str, None] = None,
            quality: DownloadQuality = "fast",
            need_video: Optional[bool] = False
    ) -> AudioDownloadResult:
        print(
            f"正在下载视频: {video_url}，保存路径: {output_dir}，质量: {quality}"
        )
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir = self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        video_data = self.fetch_video_info(video_url)
        output_path = output_path % {
            "id": video_data['aweme_detail']['aweme_id'],
            "ext": "mp3",
        }
        url = video_data['aweme_detail']['music']['play_url']['uri']
        # 下载音频
        audio_data = requests.get(url)
        with open(output_path, 'wb') as f:
            f.write(audio_data.content)
        print(url)
        tags = []
        for tag in video_data['aweme_detail']['video_tag']:
            if tag['tag_name']:
                tags.append(tag['tag_name'])

        # 获取原始标题
        original_title = video_data['aweme_detail']['item_title']
        
        # 🧹 清理标题，去掉合集相关字符串
        cleaned_title = smart_title_clean(original_title, platform="douyin", preserve_episode=False)
        logger.info(f"🧹 抖音标题清理: '{original_title}' -> '{cleaned_title}'")

        return AudioDownloadResult(
            file_path=output_path,
            title=cleaned_title,  # 使用清理后的标题
            duration=video_data['aweme_detail']['video']['duration'],
            cover_url=video_data['aweme_detail']['video']['cover_original_scale']['url_list'][0] if
            video_data['aweme_detail']['video']['cover'] else video_data['video']['big_thumbs']['img_url'],
            platform="douyin",
            video_id=video_data['aweme_detail']['aweme_id'],
            raw_info={
                'tags': video_data['aweme_detail']['caption'] + ''.join(tags),
            },
            video_path=None  # ❗音频下载不包含视频路径
        )

    def download_video(self, video_url: str, output_dir: Union[str, None] = None) -> str:

        try:

            if output_dir is None:
                output_dir = get_data_dir()
            if not output_dir:
                output_dir = self.cache_data
            os.makedirs(output_dir, exist_ok=True)

            video_id = self.extract_video_id(video_url)
            video_path = os.path.join(output_dir, f"{video_id}.mp4")
            if os.path.exists(video_path):
                return video_path


            output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

            video_data = self.fetch_video_info(video_url)
            output_path = output_path % {
                "id": video_data['aweme_detail']['aweme_id'],
                "ext": "mp4",
            }

            url=video_data['aweme_detail']['video']['download_addr']['url_list'][0]
            _data = requests.get(url,allow_redirects=True,headers=self.headers_config)

            with open(output_path, 'wb') as f:
                f.write(_data.content)

            return output_path
        except Exception as e:
            print("请求失败:", e)
            raise ValueError("请求失败:", e)



if __name__ == '__main__':
    dy = DouyinDownloader(
        cookie='')

    dy.download(
        '7.43 11/16 gba:/ j@P.xS 以"马成钢"的视角打开《抓娃娃》笼中鸟，何时飞 # 独白 # 人物故事  https://v.douyin.com/0pcFVdG_lx4/ 复制此链接，打开Dou音搜索，直接观看视频！'
    )
