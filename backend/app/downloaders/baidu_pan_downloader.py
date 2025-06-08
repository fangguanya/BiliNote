import os
import json
import time
import requests
import re
from typing import Optional, List, Dict, Tuple, Union
from urllib.parse import urlparse, parse_qs, unquote
from abc import ABC

from app.downloaders.base import Downloader, DownloadQuality, QUALITY_MAP
from app.models.notes_model import AudioDownloadResult
from app.utils.path_helper import get_data_dir
from app.services.cookie_manager import CookieConfigManager
from app.exceptions.auth_exceptions import AuthRequiredException
from app.utils.logger import get_logger
from app.utils.title_cleaner import smart_title_clean

logger = get_logger(__name__)


class BaiduPanDownloader(Downloader, ABC):
    """百度网盘下载器"""
    
    def __init__(self):
        super().__init__()
        self.cookie_manager = CookieConfigManager()
        self.session = requests.Session()
        
        # 百度网盘API相关配置
        self.api_base = "https://pan.baidu.com/api"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://pan.baidu.com/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        # 支持的视频格式
        self.video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.m2ts'}
        self.audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'}
        
        self._setup_session()

    def _setup_session(self):
        """设置会话和cookie"""
        cookie = self.cookie_manager.get("baidu_pan")
        if cookie:
            logger.info("🍪 使用已保存的百度网盘cookie")
            # 解析cookie字符串并设置到session
            for cookie_pair in cookie.split(';'):
                if '=' in cookie_pair:
                    name, value = cookie_pair.split('=', 1)
                    self.session.cookies.set(name.strip(), value.strip(), domain='.baidu.com')
            
            self.headers['Cookie'] = cookie
        else:
            logger.warning("⚠️ 未找到百度网盘cookie，部分功能可能受限")

    def _check_auth_required(self, response_data: dict) -> bool:
        """检查是否需要认证"""
        error_code = response_data.get('errno', 0)
        error_msg = response_data.get('errmsg', '')
        
        # 百度网盘常见的认证错误码
        auth_error_codes = [-6, -9, 12, 130]  # 需要登录、cookie过期、验证失败等
        
        if error_code in auth_error_codes:
            return True
            
        auth_keywords = ['登录', 'cookie', '验证', '认证', 'token']
        return any(keyword in error_msg for keyword in auth_keywords)

    def _make_request(self, url: str, params: dict = None, method: str = 'GET') -> dict:
        """发起API请求"""
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            
            response.raise_for_status()
            
            try:
                data = response.json()
            except ValueError:
                # 如果不是JSON响应，可能是HTML登录页面
                if 'login' in response.text.lower() or 'passport' in response.text.lower():
                    raise AuthRequiredException("baidu_pan", "需要登录百度网盘")
                raise Exception(f"API返回非JSON响应: {response.text[:200]}")
            
            # 检查是否需要认证
            if self._check_auth_required(data):
                raise AuthRequiredException("baidu_pan", "百度网盘认证失败，请重新登录")
            
            return data
            
        except requests.RequestException as e:
            logger.error(f"❌ 百度网盘API请求失败: {e}")
            raise Exception(f"网络请求失败: {str(e)}")

    def parse_share_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """解析分享链接，提取分享码和提取码"""
        # 分享链接格式：https://pan.baidu.com/s/1ABC123DEF?pwd=abcd
        share_match = re.search(r"/s/([0-9A-Za-z_-]+)", url)
        if not share_match:
            return None, None
            
        share_code = share_match.group(1)
        
        # 提取提取码
        pwd_match = re.search(r"[?&]pwd=([0-9A-Za-z]+)", url)
        extract_code = pwd_match.group(1) if pwd_match else None
        
        return share_code, extract_code

    def parse_path_url(self, url: str) -> str:
        """解析网盘目录URL，提取路径"""
        # 目录链接格式：https://pan.baidu.com/disk/home#/path=/视频目录
        path_match = re.search(r"#/path=([^&]+)", url)
        if path_match:
            return unquote(path_match.group(1))
        
        # 其他可能的路径格式
        dir_match = re.search(r"dir\?path=([^&]+)", url)
        if dir_match:
            return unquote(dir_match.group(1))
            
        return "/"

    def get_file_list(self, path: str = "/", share_code: str = None, extract_code: str = None) -> List[Dict]:
        """获取文件列表"""
        if share_code:
            # 分享链接的文件列表
            return self._get_share_file_list(share_code, extract_code, path)
        else:
            # 个人网盘的文件列表
            return self._get_personal_file_list(path)

    def _get_personal_file_list(self, path: str) -> List[Dict]:
        """获取个人网盘文件列表"""
        url = f"{self.api_base}/list"
        params = {
            'order': 'time',
            'desc': 1,
            'showempty': 0,
            'web': 1,
            'page': 1,
            'num': 100,
            'dir': path
        }
        
        try:
            data = self._make_request(url, params)
            
            if data.get('errno') == 0:
                file_list = data.get('list', [])
                logger.info(f"✅ 获取到 {len(file_list)} 个文件/文件夹")
                return file_list
            else:
                logger.error(f"❌ 获取文件列表失败: {data.get('errmsg')}")
                return []
                
        except Exception as e:
            logger.error(f"❌ 获取个人网盘文件列表失败: {e}")
            return []

    def _get_share_file_list(self, share_code: str, extract_code: str = None, path: str = "/") -> List[Dict]:
        """获取分享链接文件列表"""
        logger.info(f"🔗 获取分享链接文件列表: {share_code}, 提取码: {extract_code or '无'}")
        
        try:
            # 第一步：访问分享页面获取基本信息
            share_url = f"https://pan.baidu.com/s/{share_code}"
            
            response = self.session.get(
                share_url,
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"❌ 访问分享页面失败: {response.status_code}")
                return []
            
            # 从页面中提取必要的参数
            content = response.text
            
            # 提取shareid和uk
            shareid_match = re.search(r'"shareid":(\d+)', content)
            uk_match = re.search(r'"uk":(\d+)', content)
            
            if not shareid_match or not uk_match:
                logger.error("❌ 无法从分享页面提取shareid或uk")
                return []
            
            shareid = shareid_match.group(1)
            uk = uk_match.group(1)
            
            logger.info(f"📋 提取参数: shareid={shareid}, uk={uk}")
            
            # 第二步：如果有提取码，需要进行验证
            if extract_code:
                verify_url = "https://pan.baidu.com/share/verify"
                verify_data = {
                    "surl": share_code,
                    "pwd": extract_code,
                    "vcode": "",
                    "vcode_str": ""
                }
                
                verify_response = self.session.post(
                    verify_url,
                    data=verify_data,
                    headers={
                        **self.headers,
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    timeout=30
                )
                
                if verify_response.status_code != 200:
                    logger.error(f"❌ 提取码验证失败: {verify_response.status_code}")
                    return []
                
                verify_result = verify_response.json()
                if verify_result.get("errno") != 0:
                    logger.error(f"❌ 提取码错误: {verify_result.get('msg', '未知错误')}")
                    return []
                
                logger.info("✅ 提取码验证成功")
            
            # 第三步：获取文件列表
            list_url = "https://pan.baidu.com/share/list"
            params = {
                "shareid": shareid,
                "uk": uk,
                "dir": path,
                "page": 1,
                "num": 100,
                "order": "time",
                "desc": 1,
                "showempty": 0,
                "web": 1
            }
            
            list_response = self.session.get(
                list_url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            
            if list_response.status_code != 200:
                logger.error(f"❌ 获取文件列表失败: {list_response.status_code}")
                return []
            
            list_data = list_response.json()
            
            if list_data.get("errno") != 0:
                error_msg = list_data.get("errmsg", "未知错误")
                logger.error(f"❌ 文件列表API错误: {error_msg}")
                return []
            
            file_list = list_data.get("list", [])
            logger.info(f"✅ 获取到 {len(file_list)} 个文件/文件夹")
            
            return file_list
            
        except Exception as e:
            logger.error(f"❌ 获取分享链接文件列表失败: {e}")
            return []

    def filter_media_files(self, file_list: List[Dict]) -> List[Dict]:
        """过滤出媒体文件（视频和音频）"""
        media_files = []
        
        for file_info in file_list:
            if file_info.get('isdir', 0) == 1:
                # 是文件夹，跳过（可以递归处理）
                continue
                
            filename = file_info.get('server_filename', '')
            file_ext = os.path.splitext(filename)[1].lower()
            
            if file_ext in self.video_extensions or file_ext in self.audio_extensions:
                media_files.append(file_info)
                logger.info(f"📁 找到媒体文件: {filename}")
        
        return media_files

    def get_download_link(self, fs_id: str, filename: str, share_info: dict = None) -> Optional[str]:
        """获取文件下载链接"""
        
        if share_info:
            # 分享链接的下载
            return self._get_share_download_link(fs_id, filename, share_info)
        else:
            # 个人网盘的下载
            return self._get_personal_download_link(fs_id, filename)
    
    def _get_personal_download_link(self, fs_id: str, filename: str) -> Optional[str]:
        """获取个人网盘文件下载链接"""
        url = f"{self.api_base}/download"
        params = {
            'method': 'download',
            'app_id': '250528',
            'fidlist': f'[{fs_id}]',
            'type': 'dlink'
        }
        
        try:
            data = self._make_request(url, params)
            
            if data.get('errno') == 0:
                dlink_list = data.get('dlink', [])
                if dlink_list:
                    download_url = dlink_list[0].get('dlink')
                    logger.info(f"✅ 获取个人网盘下载链接成功: {filename}")
                    return download_url
            
            logger.error(f"❌ 获取个人网盘下载链接失败: {data.get('errmsg')}")
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取个人网盘下载链接失败: {e}")
            return None
    
    def _get_share_download_link(self, fs_id: str, filename: str, share_info: dict) -> Optional[str]:
        """获取分享文件下载链接"""
        try:
            shareid = share_info.get('shareid')
            uk = share_info.get('uk')
            share_code = share_info.get('share_code')
            
            if not all([shareid, uk, share_code]):
                logger.error("❌ 分享信息不完整")
                return None
            
            # 分享文件的下载链接获取
            download_url = "https://pan.baidu.com/api/sharedownload"
            params = {
                'shareid': shareid,
                'uk': uk,
                'product': 'share',
                'type': 'nolimit',
                'fidlist': f'[{fs_id}]',
                'extra': f'{{"sekey":""}}'
            }
            
            response = self.session.get(
                download_url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"❌ 分享下载链接请求失败: {response.status_code}")
                return None
            
            data = response.json()
            
            if data.get('errno') == 0:
                dlink_list = data.get('list', [])
                if dlink_list:
                    download_url = dlink_list[0].get('dlink')
                    logger.info(f"✅ 获取分享下载链接成功: {filename}")
                    return download_url
            
            # 如果直接获取失败，尝试其他方法
            logger.warning(f"⚠️ 分享下载链接获取失败，尝试备用方法: {data.get('errmsg')}")
            
            # 备用方法：通过save to my disk then download
            return self._try_alternative_share_download(fs_id, filename, share_info)
            
        except Exception as e:
            logger.error(f"❌ 获取分享下载链接失败: {e}")
            return None
    
    def _try_alternative_share_download(self, fs_id: str, filename: str, share_info: dict) -> Optional[str]:
        """分享下载的备用方法"""
        logger.info(f"🔄 尝试分享下载备用方法: {filename}")
        
        # 这里可以实现其他下载策略，比如：
        # 1. 尝试直接访问分享页面的下载按钮
        # 2. 使用第三方下载工具
        # 3. 提示用户手动下载
        
        logger.warning("⚠️ 分享文件下载需要更高级的权限或使用浏览器手动下载")
        return None

    def download_file(self, download_url: str, filename: str, output_dir: str) -> Optional[str]:
        """下载文件到本地"""
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # 清理文件名
            safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            local_path = os.path.join(output_dir, safe_filename)
            
            logger.info(f"📥 开始下载: {filename}")
            
            response = self.session.get(
                download_url,
                headers=self.headers,
                stream=True,
                timeout=60
            )
            
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"✅ 下载完成: {local_path}")
            return local_path
            
        except Exception as e:
            logger.error(f"❌ 下载文件失败 {filename}: {e}")
            return None

    def download(self, video_url: str, output_dir: str = None, 
                 quality: DownloadQuality = "fast", need_video: Optional[bool] = False) -> AudioDownloadResult:
        """
        主下载方法
        
        :param video_url: 百度网盘链接（支持分享链接和目录链接）
        :param output_dir: 输出目录
        :param quality: 质量（百度网盘中为original）
        :param need_video: 是否需要视频文件
        :return: AudioDownloadResult对象
        """
        try:
            if not output_dir:
                output_dir = get_data_dir()
            
            logger.info(f"🎯 开始处理百度网盘链接: {video_url}")
            
            # 解析URL类型
            share_code, extract_code = self.parse_share_url(video_url)
            share_info = None
            
            if share_code:
                logger.info(f"📎 检测到分享链接: {share_code}, 提取码: {extract_code or '无'}")
                
                # 首先获取分享页面的基本信息
                try:
                    share_url = f"https://pan.baidu.com/s/{share_code}"
                    response = self.session.get(share_url, headers=self.headers, timeout=30)
                    
                    if response.status_code == 200:
                        content = response.text
                        shareid_match = re.search(r'"shareid":(\d+)', content)
                        uk_match = re.search(r'"uk":(\d+)', content)
                        
                        if shareid_match and uk_match:
                            share_info = {
                                'shareid': shareid_match.group(1),
                                'uk': uk_match.group(1),
                                'share_code': share_code,
                                'extract_code': extract_code
                            }
                            logger.info(f"📋 分享信息: shareid={share_info['shareid']}, uk={share_info['uk']}")
                        else:
                            logger.warning("⚠️ 无法从分享页面提取完整信息")
                    else:
                        logger.warning(f"⚠️ 访问分享页面失败: {response.status_code}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ 获取分享页面信息失败: {e}")
                
                # 获取分享文件列表
                file_list = self.get_file_list(share_code=share_code, extract_code=extract_code)
            else:
                # 个人网盘目录
                path = self.parse_path_url(video_url)
                logger.info(f"📁 检测到个人网盘路径: {path}")
                file_list = self.get_file_list(path=path)
            
            if not file_list:
                raise Exception("未找到任何文件")
            
            # 过滤媒体文件
            media_files = self.filter_media_files(file_list)
            
            if not media_files:
                raise Exception("未找到任何媒体文件")
            
            # 如果有多个文件，选择第一个进行处理
            target_file = media_files[0]
            
            fs_id = str(target_file.get('fs_id'))
            filename = target_file.get('server_filename', f"baidu_pan_{fs_id}")
            file_size = target_file.get('size', 0)
            
            logger.info(f"📄 选择文件: {filename} (大小: {file_size} bytes)")
            
            # 获取下载链接（传递分享信息）
            download_url = self.get_download_link(fs_id, filename, share_info)
            if not download_url:
                raise Exception("获取下载链接失败")
            
            # 下载文件
            local_path = self.download_file(download_url, filename, output_dir)
            if not local_path:
                raise Exception("文件下载失败")
            
            # 获取原始标题并清理
            original_title = os.path.splitext(filename)[0]  # 去掉扩展名作为标题
            
            # 🧹 清理标题，去掉合集相关字符串
            cleaned_title = smart_title_clean(original_title, platform="baidu_pan", preserve_episode=False)
            logger.info(f"🧹 百度网盘标题清理: '{original_title}' -> '{cleaned_title}'")
            
            # 构造返回结果
            return AudioDownloadResult(
                file_path=local_path,
                title=cleaned_title,  # 使用清理后的标题
                duration=0.0,  # 百度网盘无法直接获取时长，设为0
                cover_url=None,  # 百度网盘无封面
                platform="baidu_pan",
                video_id=fs_id,
                raw_info={
                    "fs_id": fs_id,
                    "filename": filename,
                    "size": file_size,
                    "download_url": download_url,
                    "source_url": video_url,
                    "share_info": share_info
                },
                video_path=local_path if need_video else None
            )
            
        except AuthRequiredException:
            raise
        except Exception as e:
            logger.error(f"❌ 百度网盘下载失败: {e}")
            raise Exception(f"百度网盘下载失败: {str(e)}")

    def batch_download(self, video_url: str, output_dir: str = None, 
                      max_files: int = 10) -> List[AudioDownloadResult]:
        """
        批量下载目录中的所有媒体文件
        
        :param video_url: 百度网盘目录链接
        :param output_dir: 输出目录
        :param max_files: 最大文件数量
        :return: AudioDownloadResult列表
        """
        try:
            results = []
            
            if not output_dir:
                output_dir = get_data_dir()
            
            logger.info(f"🎯 开始批量处理百度网盘链接: {video_url}")
            
            # 解析URL类型
            share_code, extract_code = self.parse_share_url(video_url)
            
            if share_code:
                file_list = self.get_file_list(share_code=share_code, extract_code=extract_code)
            else:
                path = self.parse_path_url(video_url)
                file_list = self.get_file_list(path=path)
            
            if not file_list:
                logger.warning("⚠️ 未找到任何文件")
                return results
            
            # 过滤媒体文件
            media_files = self.filter_media_files(file_list)
            
            if not media_files:
                logger.warning("⚠️ 未找到任何媒体文件")
                return results
            
            # 限制文件数量
            media_files = media_files[:max_files]
            logger.info(f"📄 将处理 {len(media_files)} 个媒体文件")
            
            for i, file_info in enumerate(media_files, 1):
                try:
                    fs_id = str(file_info.get('fs_id'))
                    filename = file_info.get('server_filename', f"baidu_pan_{fs_id}")
                    file_size = file_info.get('size', 0)
                    
                    logger.info(f"📄 处理文件 {i}/{len(media_files)}: {filename}")
                    
                    # 获取下载链接
                    download_url = self.get_download_link(fs_id, filename)
                    if not download_url:
                        logger.warning(f"⚠️ 获取下载链接失败: {filename}")
                        continue
                    
                    # 下载文件
                    local_path = self.download_file(download_url, filename, output_dir)
                    if not local_path:
                        logger.warning(f"⚠️ 文件下载失败: {filename}")
                        continue
                    
                    # 获取原始标题并清理
                    original_title = os.path.splitext(filename)[0]
                    cleaned_title = smart_title_clean(original_title, platform="baidu_pan", preserve_episode=False)
                    logger.info(f"🧹 百度网盘批量标题清理: '{original_title}' -> '{cleaned_title}'")
                    
                    # 添加到结果列表
                    result = AudioDownloadResult(
                        file_path=local_path,
                        title=cleaned_title,  # 使用清理后的标题
                        duration=0.0,
                        cover_url=None,
                        platform="baidu_pan",
                        video_id=fs_id,
                        raw_info={
                            "fs_id": fs_id,
                            "filename": filename,
                            "size": file_size,
                            "download_url": download_url,
                            "source_url": video_url
                        }
                    )
                    
                    results.append(result)
                    logger.info(f"✅ 文件处理完成: {filename}")
                    
                    # 添加延迟避免请求过快
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"❌ 处理文件失败 {filename}: {e}")
                    continue
            
            logger.info(f"✅ 批量下载完成，成功处理 {len(results)} 个文件")
            return results
            
        except Exception as e:
            logger.error(f"❌ 批量下载失败: {e}")
            return []

    @staticmethod  
    def download_video(video_url: str, output_dir: Union[str, None] = None) -> str:
        """
        下载视频文件（静态方法，保持接口兼容性）
        """
        downloader = BaiduPanDownloader()
        result = downloader.download(video_url, output_dir, need_video=True)
        return result.video_path or result.file_path 