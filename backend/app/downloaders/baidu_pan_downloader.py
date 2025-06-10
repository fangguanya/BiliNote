import os
import json
import time
import requests
import re
from typing import Optional, List, Dict, Tuple, Union
from urllib.parse import urlparse, parse_qs, unquote


from app.downloaders.base import Downloader, DownloadQuality, QUALITY_MAP
from app.models.notes_model import AudioDownloadResult
from app.utils.path_helper import get_data_dir
from app.services.cookie_manager import CookieConfigManager
from app.services.baidupcs_service import BaiduPCSService as NewBaiduPCSService
from app.services.baidu_pcs_service import BaiduFileInfo, RapidUploadInfo
from app.exceptions.auth_exceptions import AuthRequiredException
from app.utils.logger import get_logger
from app.utils.title_cleaner import smart_title_clean

logger = get_logger(__name__)


class BaiduPanDownloader(Downloader):
    """
    百度网盘下载器 - 升级版
    集成BaiduPCS-Py设计理念，支持更完整的功能
    """
    
    def __init__(self):
        super().__init__()
        
        # 使用新的BaiduPCS服务
        self.new_pcs_service = NewBaiduPCSService()
        
        # 保持旧版兼容性
        self.cookie_manager = CookieConfigManager()
        
        # 百度网盘API相关配置
        self.api_base = "https://pan.baidu.com/api"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://pan.baidu.com/',
            'Accept': 'application/json, text/plain, */*',
        }
        
        # 支持的视频格式（扩展）
        self.video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.m2ts', '.f4v', '.rmvb', '.rm'}
        self.audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.ape', '.ac3', '.dts'}
        
        # 关键cookie名称
        self.critical_cookies = ['BDUSS', 'STOKEN', 'PSTM']
        self.optional_cookies = ['BAIDUID', 'BAIDUID_BFESS', 'PASSID', 'UBI', 'UBI_BFESS', 'PANPSC']

    def _setup_session(self):
        """设置会话和cookie（使用PCS服务）"""
        # 已由PCS服务处理
        pass

    def _check_auth_required(self, response_data: dict) -> bool:
        """检查是否需要认证"""
        error_code = response_data.get('errno', 0)
        error_msg = response_data.get('errmsg', '')
        
        # 百度网盘常见的认证错误码
        auth_error_codes = [-6, -9, 12, 130, 2, 31119, 31329]
        
        if error_code in auth_error_codes:
            return True
            
        # 检查错误消息中的认证关键词
        auth_keywords = ['登录', 'cookie', '验证', '认证', 'token', 'unauthorized', 'forbidden', 'access denied']
        error_msg_lower = error_msg.lower() if error_msg else ''
        return any(keyword in error_msg_lower for keyword in auth_keywords)

    def _validate_cookie_status(self) -> bool:
        """验证当前cookie状态"""
        try:
            return self.new_pcs_service.is_authenticated()
        except Exception as e:
            logger.warning(f"⚠️ Cookie验证失败: {e}")
            return False

    def _make_request(self, url: str, params: dict = None, method: str = 'GET') -> dict:
        """发起API请求（使用新PCS服务）"""
        # 暂时使用简单的requests调用，因为新服务结构不同
        import requests
        try:
            response = requests.request(method, url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"❌ API请求失败: {e}")
            return {"errno": -1, "errmsg": str(e)}

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
        # 处理baidu_pan://协议
        if url.startswith("baidu_pan://file/"):
            # baidu_pan://file/fs_id?filename=xxx&path=xxx
            # 从path参数中提取目录路径
            path_match = re.search(r"[?&]path=([^&]+)", url)
            if path_match:
                full_path = unquote(path_match.group(1))
                # 提取目录部分（去掉文件名）
                return os.path.dirname(full_path) or "/"
            return "/"
        
        # 目录链接格式：https://pan.baidu.com/disk/home#/path=/视频目录
        path_match = re.search(r"#/path=([^&]+)", url)
        if path_match:
            return unquote(path_match.group(1))
        
        # 其他可能的路径格式
        dir_match = re.search(r"dir\?path=([^&]+)", url)
        if dir_match:
            return unquote(dir_match.group(1))
            
        return "/"

    def is_rapid_upload_link(self, url: str) -> bool:
        """判断是否为秒传链接"""
        # cs3l协议
        if url.startswith('cs3l://'):
            return True
        
        # bdpan协议
        if url.startswith('bdpan://'):
            return True
        
        # 简化格式：md5#slice_md5#size#filename 或 md5#slice_md5#crc32#size#filename
        # 检查是否符合秒传链接的基本格式
        if '#' in url and not url.startswith('http'):
            parts = url.split('#')
            if len(parts) >= 4:
                # 检查md5格式（32位十六进制）
                try:
                    if len(parts[0]) == 32 and len(parts[1]) == 32:
                        # 检查第三个或第四个参数是否为数字（文件大小）
                        if len(parts) == 4:
                            int(parts[2])  # 文件大小
                            return True
                        elif len(parts) >= 5:
                            int(parts[3])  # 文件大小
                            return True
                except ValueError:
                    pass
        
        return False
    
    def parse_baidu_pan_url(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """解析baidu_pan://协议链接
        
        Returns:
            (fs_id, filename, path) - 文件ID、文件名、完整路径
        """
        if not url.startswith("baidu_pan://file/"):
            return None, None, None
            
        # 格式: baidu_pan://file/fs_id?filename=xxx&path=xxx
        match = re.search(r"baidu_pan://file/([^?]+)", url)
        if not match:
            return None, None, None
            
        fs_id = match.group(1)
        
        # 提取filename参数
        filename_match = re.search(r"[?&]filename=([^&]+)", url)
        filename = unquote(filename_match.group(1)) if filename_match else None
        
        # 提取path参数
        path_match = re.search(r"[?&]path=([^&]+)", url)
        path = unquote(path_match.group(1)) if path_match else None
        
        return fs_id, filename, path

    def get_file_list(self, path: str = "/", share_code: str = None, extract_code: str = None) -> List[Dict]:
        """获取文件列表"""
        if share_code:
            # 分享链接的文件列表
            return self._get_share_file_list(share_code, extract_code, path)
        else:
            # 个人网盘的文件列表
            return self._get_personal_file_list(path)

    def _get_personal_file_list(self, path: str) -> List[Dict]:
        """获取个人网盘文件列表（使用新BaiduPCS服务）"""
        logger.info(f"📂 获取个人网盘文件列表: {path}")
        
        try:
            # 使用新的BaiduPCS服务
            result = self.new_pcs_service.get_file_list(path=path)
            
            if not result.get("success", False):
                logger.error(f"❌ 获取文件列表失败: {result.get('message', '未知错误')}")
                return []
            
            files_data = result.get("files", [])
            
            # 转换为旧格式以保持兼容性
            file_list = []
            for file_info in files_data:
                file_dict = {
                    'fs_id': file_info.get('fs_id', ''),
                    'server_filename': file_info.get('filename', ''),
                    'path': file_info.get('path', ''),
                    'size': file_info.get('size', 0),
                    'md5': '',  # 新服务暂不提供md5
                    'isdir': 1 if file_info.get('is_dir', False) else 0,
                    'server_ctime': file_info.get('ctime', 0),
                    'server_mtime': file_info.get('mtime', 0),
                    'category': 1 if file_info.get('is_media', False) else 6  # 1=视频 6=其他
                }
                file_list.append(file_dict)
            
            logger.info(f"✅ 获取到 {len(file_list)} 个文件/文件夹")
            return file_list
            
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
            category = file_info.get('category', 6)
            
            # 根据扩展名或类别判断是否为媒体文件
            is_media = (file_ext in self.video_extensions or 
                       file_ext in self.audio_extensions or
                       category in [1, 2])  # 1视频 2音频
            
            if is_media:
                media_files.append(file_info)
                logger.info(f"📁 找到媒体文件: {filename}")
        
        return media_files

    def get_download_link(self, fs_id: str, filename: str, share_info: dict = None) -> Optional[str]:
        """获取文件下载链接"""
        
        if share_info:
            # 分享链接的下载
            return self._get_share_download_link(fs_id, filename, share_info)
        else:
            # 个人网盘的下载（使用PCS服务）
            return self._get_personal_download_link(fs_id, filename)
    
    def _get_personal_download_link(self, fs_id: str, filename: str) -> Optional[str]:
        """获取个人网盘文件下载链接（使用新BaiduPCS服务）"""
        logger.error(f"❌ 个人网盘直接下载功能暂时不可用: {filename}")
        logger.info(f"💡 建议使用以下方法之一:")
        logger.info(f"   1. 使用分享链接下载")
        logger.info(f"   2. 手动下载后上传到系统")
        logger.info(f"   3. 等待完整的BaiduPCS下载功能实现")
        
        # 返回None表示获取下载链接失败
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
            
            # 使用特殊的User-Agent来下载百度网盘文件
            download_headers = {
                **self.headers,
                'User-Agent': 'pan.baidu.com'
            }
            
            response = self.session.get(
                download_url,
                headers=download_headers,
                stream=True,
                timeout=60
            )
            
            response.raise_for_status()
            
            # 检查文件大小
            total_size = int(response.headers.get('content-length', 0))
            if total_size > 0:
                logger.info(f"📊 文件大小: {total_size // 1024 // 1024}MB")
            
            downloaded_size = 0
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # 显示下载进度（每10MB显示一次）
                        if downloaded_size % (10 * 1024 * 1024) == 0:
                            if total_size > 0:
                                progress = (downloaded_size / total_size) * 100
                                logger.info(f"📥 下载进度: {progress:.1f}%")
            
            logger.info(f"✅ 下载完成: {local_path}")
            return local_path
            
        except Exception as e:
            logger.error(f"❌ 下载文件失败 {filename}: {e}")
            return None

    def handle_rapid_upload(self, rapid_link: str, target_dir: str = "/") -> AudioDownloadResult:
        """
        处理秒传链接
        
        :param rapid_link: 秒传链接
        :param target_dir: 目标目录（网盘路径）
        :return: AudioDownloadResult对象
        """
        logger.info(f"⚡ 处理秒传链接: {rapid_link}")
        
        try:
            # 秒传功能暂时禁用，需要适配新的BaiduPCS服务
            logger.error("❌ 秒传功能暂时不可用，需要适配新的BaiduPCS服务")
            raise Exception("秒传功能暂时不可用")
                
        except Exception as e:
            logger.error(f"❌ 秒传处理失败: {e}")
            raise Exception(f"秒传处理失败: {str(e)}")

    def download(self, video_url: str, output_dir: str = None, 
                 quality: DownloadQuality = "fast", need_video: Optional[bool] = False) -> AudioDownloadResult:
        """
        主下载方法
        
        :param video_url: 百度网盘链接（支持分享链接、目录链接、秒传链接）
        :param output_dir: 输出目录
        :param quality: 质量（百度网盘中为original）
        :param need_video: 是否需要视频文件
        :return: AudioDownloadResult对象
        """
        try:
            if not output_dir:
                output_dir = get_data_dir()
            
            logger.info(f"🎯 开始处理百度网盘链接: {video_url}")
            
            # 检查是否为秒传链接
            if self.is_rapid_upload_link(video_url):
                logger.info("🔗 检测到秒传链接")
                return self.handle_rapid_upload(video_url, target_dir="/秒传文件")
            
            # 检查是否为baidu_pan://协议链接
            fs_id, filename, file_path = self.parse_baidu_pan_url(video_url)
            if fs_id and filename:
                logger.info(f"🎯 检测到baidu_pan协议链接: fs_id={fs_id}, filename={filename}")
                
                # 直接使用指定的文件信息，无需搜索
                target_file = {
                    'fs_id': fs_id,
                    'server_filename': filename,
                    'path': file_path or f"/{filename}",
                    'size': 0,  # 大小未知
                    'isdir': 0,
                    'category': 1  # 假设是视频
                }
                
                # 获取下载链接
                download_url = self.get_download_link(fs_id, filename)
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
                        "size": 0,
                        "download_url": download_url,
                        "source_url": video_url,
                        "file_path": file_path
                    },
                    video_path=local_path if need_video else None
                )
            
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
            
            # 如果是秒传链接，只处理单个文件
            if self.is_rapid_upload_link(video_url):
                result = self.handle_rapid_upload(video_url)
                return [result]
            
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

    def batch_rapid_upload(self, rapid_links: List[str], target_dir: str = "/") -> List[AudioDownloadResult]:
        """
        批量秒传
        
        :param rapid_links: 秒传链接列表
        :param target_dir: 目标目录
        :return: AudioDownloadResult列表
        """
        logger.info(f"⚡ 批量秒传: {len(rapid_links)} 个文件")
        
        results = []
        
        for i, link in enumerate(rapid_links, 1):
            try:
                logger.info(f"⚡ 处理秒传 {i}/{len(rapid_links)}: {link}")
                result = self.handle_rapid_upload(link, target_dir)
                results.append(result)
                
                # 添加延迟避免请求过快
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ 秒传失败 {link}: {e}")
                continue
        
        logger.info(f"✅ 批量秒传完成: 成功 {len(results)}/{len(rapid_links)} 个")
        return results

    @staticmethod  
    def download_video(video_url: str, output_dir: Union[str, None] = None) -> str:
        """
        下载视频文件（静态方法，保持接口兼容性）
        """
        downloader = BaiduPanDownloader()
        result = downloader.download(video_url, output_dir, need_video=True)
        return result.video_path or result.file_path 