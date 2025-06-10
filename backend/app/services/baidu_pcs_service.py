import os
import json
import time
import requests
import hashlib
import re
from typing import Optional, List, Dict, Tuple, Union, Any
from urllib.parse import urlparse, parse_qs, unquote, quote
from dataclasses import dataclass
from pathlib import Path

from app.utils.logger import get_logger
from app.services.cookie_manager import CookieConfigManager
from app.exceptions.auth_exceptions import AuthRequiredException
from app.utils.path_helper import get_data_dir

logger = get_logger(__name__)


@dataclass
class BaiduFileInfo:
    """百度网盘文件信息"""
    fs_id: str
    filename: str
    path: str
    size: int
    md5: Optional[str] = None
    is_dir: bool = False
    server_ctime: int = 0
    server_mtime: int = 0
    category: int = 0  # 文件类型：1视频 2音频 3图片 4文档 5应用 6其他 7种子
    share_id: Optional[str] = None
    share_uk: Optional[str] = None


@dataclass
class RapidUploadInfo:
    """秒传信息"""
    content_md5: str
    slice_md5: str
    content_length: int
    filename: str
    content_crc32: Optional[int] = None
    
    def to_cs3l_link(self) -> str:
        """转换为cs3l协议链接"""
        return f"cs3l://{self.content_md5}#{self.slice_md5}#{self.content_crc32 or 0}#{self.content_length}#{self.filename}"
    
    def to_simple_link(self) -> str:
        """转换为简化链接"""
        return f"{self.content_md5}#{self.slice_md5}#{self.content_length}#{self.filename}"


@dataclass
class ShareInfo:
    """分享信息"""
    share_id: str
    uk: str
    share_code: str
    extract_code: Optional[str] = None
    share_url: str = ""
    title: str = ""
    expiry_time: int = 0


@dataclass
class DownloadTask:
    """下载任务"""
    task_id: str
    task_name: str
    status: int  # 0:下载中 1:下载成功 2:下载失败 3:下载暂停 4:等待中
    file_size: int
    finished_size: int
    create_time: int
    finish_time: int = 0
    source_url: str = ""
    save_path: str = ""


class BaiduPCSService:
    """
    百度网盘PCS服务，参考BaiduPCS-Py设计
    提供完整的百度网盘操作功能
    """
    
    def __init__(self):
        self.cookie_manager = CookieConfigManager()
        self.session = requests.Session()
        
        # API端点配置
        self.api_base = "https://pan.baidu.com/api"
        self.rest_api_base = "https://pan.baidu.com/rest/2.0/xpan"
        self.pcs_base = "https://pcs.baidu.com/rest/2.0/pcs"
        
        # 应用配置
        self.app_id = "250528"
        self.client_type = "0"
        self.web = "1"
        
        # HTTP配置
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://pan.baidu.com/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin'
        }
        
        # 认证相关
        self.critical_cookies = ['BDUSS', 'STOKEN', 'PSTM']
        self.optional_cookies = ['BAIDUID', 'BAIDUID_BFESS', 'PASSID', 'UBI', 'UBI_BFESS', 'PANPSC']
        
        # 文件类型映射
        self.category_map = {
            1: 'video',    # 视频
            2: 'audio',    # 音频  
            3: 'image',    # 图片
            4: 'doc',      # 文档
            5: 'app',      # 应用
            6: 'other',    # 其他
            7: 'torrent'   # 种子
        }
        
        # 媒体文件扩展名
        self.video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.m2ts', '.f4v', '.rmvb', '.rm'}
        self.audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.ape', '.ac3', '.dts'}
        
        self._setup_session()
    
    def _setup_session(self):
        """设置会话和认证"""
        cookie = self.cookie_manager.get("baidu_pan")
        if cookie:
            logger.info("🍪 加载百度网盘认证信息")
            
            # 解析并设置cookie
            cookie_count = 0
            parsed_cookies = {}
            
            for cookie_pair in cookie.split(';'):
                if '=' in cookie_pair:
                    name, value = cookie_pair.split('=', 1)
                    name = name.strip()
                    value = value.strip()
                    
                    if name and value:
                        self.session.cookies.set(name, value, domain='.baidu.com')
                        parsed_cookies[name] = value
                        cookie_count += 1
            
            logger.info(f"📊 设置了 {cookie_count} 个cookie")
            
            # 检查关键认证cookie
            missing_critical = [c for c in self.critical_cookies if c not in parsed_cookies]
            if missing_critical:
                logger.warning(f"⚠️ 缺少关键cookie: {missing_critical}")
            else:
                logger.info("✅ 认证cookie完整")
            
            self.headers['Cookie'] = cookie
            
            # 获取额外的认证信息
            self._extract_auth_tokens()
        else:
            logger.warning("⚠️ 未找到百度网盘认证信息")
    
    def _extract_auth_tokens(self):
        """提取认证令牌"""
        try:
            # 访问网盘首页获取必要的token
            response = self.session.get("https://pan.baidu.com/disk/home", headers=self.headers, timeout=15)
            if response.status_code == 200:
                content = response.text
                
                # 提取bdstoken
                bdstoken_match = re.search(r'"bdstoken":"([^"]+)"', content)
                if bdstoken_match:
                    self.bdstoken = bdstoken_match.group(1)
                    logger.debug("🔑 获取到bdstoken")
                
                # 提取logid
                logid_match = re.search(r'"logid":"([^"]+)"', content)
                if logid_match:
                    self.logid = logid_match.group(1)
                
                # 提取其他可能需要的参数
                clienttype_match = re.search(r'"clienttype":(\d+)', content)
                if clienttype_match:
                    self.client_type = clienttype_match.group(1)
                    
        except Exception as e:
            logger.debug(f"提取认证令牌失败: {e}")
    
    def _make_request(self, url: str, params: dict = None, data: dict = None, 
                     method: str = 'GET', **kwargs) -> dict:
        """统一的请求方法"""
        try:
            # 添加通用参数
            if params is None:
                params = {}
            
            # 添加时间戳防缓存
            params['t'] = int(time.time() * 1000)
            
            # 添加认证参数
            if hasattr(self, 'bdstoken') and self.bdstoken:
                if method.upper() == 'POST':
                    if data is None:
                        data = {}
                    data['bdstoken'] = self.bdstoken
                else:
                    params['bdstoken'] = self.bdstoken
            
            # 发起请求
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                headers=self.headers,
                timeout=kwargs.get('timeout', 30),
                **{k: v for k, v in kwargs.items() if k != 'timeout'}
            )
            
            response.raise_for_status()
            
            # 解析响应
            try:
                result = response.json()
            except ValueError:
                logger.warning(f"⚠️ 非JSON响应: {response.text[:200]}")
                if 'login' in response.text.lower():
                    raise AuthRequiredException("baidu_pan", "需要重新登录")
                raise Exception(f"API返回非JSON响应")
            
            # 检查错误
            errno = result.get('errno', 0)
            if errno != 0:
                errmsg = result.get('errmsg', f'错误码: {errno}')
                logger.warning(f"⚠️ API错误: errno={errno}, errmsg={errmsg}")
                
                # 认证相关错误
                if errno in [-6, -9, 12, 130, 2, 31119, 31329]:
                    raise AuthRequiredException("baidu_pan", f"认证失败: {errmsg}")
                
                # 其他业务错误根据具体情况处理
                if errno not in [0]:  # 某些业务场景下的非0返回码可能是正常的
                    logger.error(f"❌ API业务错误: {errmsg}")
            
            return result
            
        except requests.RequestException as e:
            logger.error(f"❌ 网络请求失败: {e}")
            raise Exception(f"网络请求失败: {str(e)}")
    
    def get_user_info(self) -> Dict[str, Any]:
        """获取用户信息"""
        logger.info("👤 获取用户信息")
        
        url = f"{self.api_base}/uinfo"
        result = self._make_request(url)
        
        if result.get('errno') == 0:
            user_info = result.get('user_info', {})
            logger.info(f"✅ 当前用户: {user_info.get('baidu_name', '未知')}")
            return user_info
        else:
            raise Exception(f"获取用户信息失败: {result.get('errmsg')}")
    
    def get_quota_info(self) -> Dict[str, Any]:
        """获取网盘配额信息"""
        logger.info("💾 获取网盘配额信息")
        
        url = f"{self.rest_api_base}/quota"
        params = {
            'checkfree': 1,
            'checkexpire': 1
        }
        
        result = self._make_request(url, params)
        
        if result.get('errno') == 0:
            total = result.get('total', 0)
            used = result.get('used', 0)
            free = total - used
            
            logger.info(f"📊 网盘空间: 总计{total//1024//1024//1024}GB, 已用{used//1024//1024//1024}GB, 剩余{free//1024//1024//1024}GB")
            return {
                'total': total,
                'used': used,
                'free': free
            }
        else:
            raise Exception(f"获取配额信息失败: {result.get('errmsg')}")
    
    def list_files(self, path: str = "/", order: str = "time", desc: int = 1, 
                  start: int = 0, limit: int = 100, recursion: int = 0) -> List[BaiduFileInfo]:
        """
        获取文件列表
        
        :param path: 目录路径
        :param order: 排序方式 time/name/size
        :param desc: 是否降序 1降序 0升序
        :param start: 起始位置
        :param limit: 限制数量
        :param recursion: 是否递归 1递归 0不递归
        :return: 文件信息列表
        """
        logger.info(f"📂 获取文件列表: {path}")
        
        url = f"{self.rest_api_base}/file"
        params = {
            'method': 'list',
            'dir': path,
            'order': order,
            'desc': desc,
            'start': start,
            'limit': limit,
            'web': self.web,
            'folder': 0,
            'showempty': 0,
            'recursion': recursion
        }
        
        result = self._make_request(url, params)
        
        if result.get('errno') == 0:
            file_list = result.get('list', [])
            logger.info(f"✅ 获取到 {len(file_list)} 个文件/文件夹")
            
            # 转换为BaiduFileInfo对象
            files = []
            for file_data in file_list:
                file_info = BaiduFileInfo(
                    fs_id=str(file_data.get('fs_id', '')),
                    filename=file_data.get('server_filename', ''),
                    path=file_data.get('path', ''),
                    size=file_data.get('size', 0),
                    md5=file_data.get('md5'),
                    is_dir=file_data.get('isdir', 0) == 1,
                    server_ctime=file_data.get('server_ctime', 0),
                    server_mtime=file_data.get('server_mtime', 0),
                    category=file_data.get('category', 6)
                )
                files.append(file_info)
            
            return files
        else:
            raise Exception(f"获取文件列表失败: {result.get('errmsg')}")
    
    def search_files(self, keyword: str, path: str = "/", recursion: int = 1, 
                    page: int = 1, num: int = 100) -> List[BaiduFileInfo]:
        """
        搜索文件
        
        :param keyword: 搜索关键词
        :param path: 搜索路径
        :param recursion: 是否递归搜索
        :param page: 页码
        :param num: 每页数量
        :return: 文件信息列表
        """
        logger.info(f"🔍 搜索文件: {keyword}")
        
        url = f"{self.rest_api_base}/file"
        params = {
            'method': 'search',
            'key': keyword,
            'dir': path,
            'recursion': recursion,
            'page': page,
            'num': num,
            'web': self.web
        }
        
        result = self._make_request(url, params)
        
        if result.get('errno') == 0:
            file_list = result.get('list', [])
            logger.info(f"✅ 搜索到 {len(file_list)} 个文件")
            
            files = []
            for file_data in file_list:
                file_info = BaiduFileInfo(
                    fs_id=str(file_data.get('fs_id', '')),
                    filename=file_data.get('server_filename', ''),
                    path=file_data.get('path', ''),
                    size=file_data.get('size', 0),
                    md5=file_data.get('md5'),
                    is_dir=file_data.get('isdir', 0) == 1,
                    server_ctime=file_data.get('server_ctime', 0),
                    server_mtime=file_data.get('server_mtime', 0),
                    category=file_data.get('category', 6)
                )
                files.append(file_info)
            
            return files
        else:
            raise Exception(f"搜索文件失败: {result.get('errmsg')}")
    
    def get_download_links(self, fs_ids: List[str], quality: str = "origin") -> List[Dict[str, Any]]:
        """
        获取下载链接
        
        :param fs_ids: 文件fs_id列表
        :param quality: 下载质量 origin/high/medium/low
        :return: 下载链接信息列表
        """
        logger.info(f"📥 获取下载链接: {len(fs_ids)} 个文件")
        
        url = f"{self.rest_api_base}/file"
        params = {
            'method': 'filemetas',
            'fsids': json.dumps([int(fs_id) for fs_id in fs_ids]),
            'dlink': 1,
            'thumb': 0,
            'extra': 1,
            'needmedia': 1 if quality != "origin" else 0,
            'detail': 1
        }
        
        result = self._make_request(url, params)
        
        if result.get('errno') == 0:
            file_list = result.get('list', [])
            logger.info(f"✅ 获取到 {len(file_list)} 个下载链接")
            
            download_info = []
            for file_data in file_list:
                info = {
                    'fs_id': str(file_data.get('fs_id', '')),
                    'filename': file_data.get('filename', ''),
                    'size': file_data.get('size', 0),
                    'dlink': file_data.get('dlink', ''),
                }
                
                # 处理媒体质量链接
                if quality != "origin" and 'thumbs' in file_data:
                    thumbs = file_data['thumbs']
                    if quality in thumbs:
                        info['dlink'] = thumbs[quality].get('url', info['dlink'])
                
                download_info.append(info)
            
            return download_info
        else:
            raise Exception(f"获取下载链接失败: {result.get('errmsg')}")
    
    def rapid_upload(self, rapid_info: RapidUploadInfo, target_path: str) -> bool:
        """
        秒传文件
        
        :param rapid_info: 秒传信息
        :param target_path: 目标路径
        :return: 是否成功
        """
        logger.info(f"⚡ 秒传文件: {rapid_info.filename}")
        
        url = f"{self.rest_api_base}/file"
        data = {
            'method': 'rapidupload',
            'path': target_path,
            'content-md5': rapid_info.content_md5,
            'slice-md5': rapid_info.slice_md5,
            'content-length': rapid_info.content_length,
            'content-crc32': rapid_info.content_crc32 or 0,
            'rtype': 1
        }
        
        result = self._make_request(url, data=data, method='POST')
        
        if result.get('errno') == 0:
            logger.info(f"✅ 秒传成功: {rapid_info.filename}")
            return True
        elif result.get('errno') == -8:
            logger.warning(f"⚠️ 文件已存在: {rapid_info.filename}")
            return False
        else:
            logger.error(f"❌ 秒传失败: {result.get('errmsg')}")
            return False
    
    def parse_rapid_upload_link(self, link: str) -> Optional[RapidUploadInfo]:
        """
        解析秒传链接
        
        :param link: 秒传链接 (cs3l://或简化格式)
        :return: 秒传信息
        """
        try:
            # cs3l协议格式: cs3l://content_md5#slice_md5#crc32#length#filename
            if link.startswith('cs3l://'):
                link = link[7:]  # 去掉协议前缀
            
            # bdpan协议格式需要base64解码
            if link.startswith('bdpan://'):
                import base64
                encoded = link[8:]
                decoded = base64.b64decode(encoded).decode('utf-8')
                # 格式: filename|size|content_md5|slice_md5
                parts = decoded.split('|')
                if len(parts) >= 4:
                    return RapidUploadInfo(
                        filename=parts[0],
                        content_length=int(parts[1]),
                        content_md5=parts[2],
                        slice_md5=parts[3]
                    )
            
            # 简化格式: content_md5#slice_md5#length#filename
            # 或完整格式: content_md5#slice_md5#crc32#length#filename
            parts = link.split('#')
            if len(parts) >= 4:
                if len(parts) == 4:
                    # 简化格式
                    content_md5, slice_md5, length, filename = parts
                    crc32 = None
                else:
                    # 完整格式
                    content_md5, slice_md5, crc32, length, filename = parts[:5]
                    try:
                        crc32 = int(crc32) if crc32 and crc32.isdigit() else None
                    except:
                        crc32 = None
                
                return RapidUploadInfo(
                    content_md5=content_md5,
                    slice_md5=slice_md5,
                    content_length=int(length),
                    filename=filename,
                    content_crc32=crc32
                )
            
            logger.warning(f"⚠️ 无法解析秒传链接: {link}")
            return None
            
        except Exception as e:
            logger.error(f"❌ 解析秒传链接失败: {e}")
            return None
    
    def create_share(self, fs_ids: List[str], password: str = "", period: int = 0) -> ShareInfo:
        """
        创建分享链接
        
        :param fs_ids: 文件fs_id列表
        :param password: 提取码(4位)
        :param period: 有效期天数(0永久 1一天 7七天)
        :return: 分享信息
        """
        logger.info(f"🔗 创建分享链接: {len(fs_ids)} 个文件")
        
        url = f"{self.rest_api_base}/share"
        data = {
            'method': 'set',
            'fid_list': json.dumps([int(fs_id) for fs_id in fs_ids]),
            'schannel': 4,
            'channel_list': '[]',
            'period': period
        }
        
        if password:
            data['pwd'] = password
        
        result = self._make_request(url, data=data, method='POST')
        
        if result.get('errno') == 0:
            share_id = str(result.get('shareid', ''))
            uk = str(result.get('uk', ''))
            share_code = result.get('link', '').split('/')[-1] if result.get('link') else ''
            
            share_info = ShareInfo(
                share_id=share_id,
                uk=uk,
                share_code=share_code,
                extract_code=password,
                share_url=result.get('link', ''),
                expiry_time=result.get('expiry_time', 0)
            )
            
            logger.info(f"✅ 分享链接创建成功: {share_info.share_url}")
            return share_info
        else:
            raise Exception(f"创建分享链接失败: {result.get('errmsg')}")
    
    def list_shares(self, page: int = 1, num: int = 100) -> List[ShareInfo]:
        """
        获取分享列表
        
        :param page: 页码
        :param num: 每页数量
        :return: 分享信息列表
        """
        logger.info("📋 获取分享列表")
        
        url = f"{self.rest_api_base}/share"
        params = {
            'method': 'list',
            'page': page,
            'num': num,
            'order': 'ctime',
            'desc': 1
        }
        
        result = self._make_request(url, params)
        
        if result.get('errno') == 0:
            share_list = result.get('list', [])
            logger.info(f"✅ 获取到 {len(share_list)} 个分享")
            
            shares = []
            for share_data in share_list:
                share_info = ShareInfo(
                    share_id=str(share_data.get('shareid', '')),
                    uk=str(share_data.get('uk', '')),
                    share_code=share_data.get('shorturl', '').split('/')[-1] if share_data.get('shorturl') else '',
                    share_url=share_data.get('shorturl', ''),
                    title=share_data.get('title', ''),
                    expiry_time=share_data.get('expiry_time', 0)
                )
                shares.append(share_info)
            
            return shares
        else:
            raise Exception(f"获取分享列表失败: {result.get('errmsg')}")
    
    def cancel_share(self, share_ids: List[str]) -> bool:
        """
        取消分享
        
        :param share_ids: 分享ID列表
        :return: 是否成功
        """
        logger.info(f"🗑️ 取消分享: {len(share_ids)} 个")
        
        url = f"{self.rest_api_base}/share"
        data = {
            'method': 'cancel',
            'shareid_list': json.dumps([int(sid) for sid in share_ids])
        }
        
        result = self._make_request(url, data=data, method='POST')
        
        if result.get('errno') == 0:
            logger.info("✅ 取消分享成功")
            return True
        else:
            logger.error(f"❌ 取消分享失败: {result.get('errmsg')}")
            return False
    
    def add_offline_task(self, source_url: str, save_path: str, 
                        file_types: List[str] = None) -> str:
        """
        添加离线下载任务
        
        :param source_url: 源URL (magnet/http/https)
        :param save_path: 保存路径
        :param file_types: 文件类型过滤 ['m', 'i', 'd', 'c', 'a'] 媒体/图片/文档/压缩/全部
        :return: 任务ID
        """
        logger.info(f"📥 添加离线下载任务: {source_url}")
        
        url = f"{self.rest_api_base}/services/cloud_dl"
        data = {
            'method': 'add_task',
            'source_url': source_url,
            'save_path': save_path,
            'type': 4 if source_url.startswith('magnet:') else 3
        }
        
        # 种子文件类型过滤
        if source_url.startswith('magnet:') and file_types:
            type_map = {'m': 1, 'i': 2, 'd': 3, 'c': 4, 'a': 0}
            selected_types = [type_map.get(t, 0) for t in file_types if t in type_map]
            if selected_types:
                data['selected_idx'] = json.dumps(selected_types)
        
        result = self._make_request(url, data=data, method='POST')
        
        if result.get('errno') == 0:
            task_id = str(result.get('task_id', ''))
            logger.info(f"✅ 离线任务创建成功: {task_id}")
            return task_id
        else:
            raise Exception(f"添加离线任务失败: {result.get('errmsg')}")
    
    def list_offline_tasks(self, start: int = 0, limit: int = 100) -> List[DownloadTask]:
        """
        获取离线下载任务列表
        
        :param start: 起始位置
        :param limit: 限制数量
        :return: 任务列表
        """
        logger.info("📋 获取离线任务列表")
        
        url = f"{self.rest_api_base}/services/cloud_dl"
        params = {
            'method': 'list_task',
            'start': start,
            'limit': limit,
            'asc': 0,
            'source': ''
        }
        
        result = self._make_request(url, params)
        
        if result.get('errno') == 0:
            task_list = result.get('task_info', [])
            logger.info(f"✅ 获取到 {len(task_list)} 个离线任务")
            
            tasks = []
            for task_data in task_list:
                task = DownloadTask(
                    task_id=str(task_data.get('task_id', '')),
                    task_name=task_data.get('task_name', ''),
                    status=task_data.get('status', 0),
                    file_size=task_data.get('file_size', 0),
                    finished_size=task_data.get('finished_size', 0),
                    create_time=task_data.get('create_time', 0),
                    finish_time=task_data.get('finish_time', 0),
                    source_url=task_data.get('source_url', ''),
                    save_path=task_data.get('save_path', '')
                )
                tasks.append(task)
            
            return tasks
        else:
            raise Exception(f"获取离线任务失败: {result.get('errmsg')}")
    
    def cancel_offline_task(self, task_ids: List[str]) -> bool:
        """
        取消离线下载任务
        
        :param task_ids: 任务ID列表
        :return: 是否成功
        """
        logger.info(f"❌ 取消离线任务: {len(task_ids)} 个")
        
        url = f"{self.rest_api_base}/services/cloud_dl"
        data = {
            'method': 'cancel_task',
            'task_ids': json.dumps([int(tid) for tid in task_ids])
        }
        
        result = self._make_request(url, data=data, method='POST')
        
        if result.get('errno') == 0:
            logger.info("✅ 取消离线任务成功")
            return True
        else:
            logger.error(f"❌ 取消离线任务失败: {result.get('errmsg')}")
            return False
    
    def clear_offline_tasks(self) -> bool:
        """清除已完成和失败的离线任务"""
        logger.info("🧹 清除离线任务")
        
        url = f"{self.rest_api_base}/services/cloud_dl"
        data = {'method': 'clear_task'}
        
        result = self._make_request(url, data=data, method='POST')
        
        if result.get('errno') == 0:
            logger.info("✅ 清除离线任务成功")
            return True
        else:
            logger.error(f"❌ 清除离线任务失败: {result.get('errmsg')}")
            return False
    
    def filter_media_files(self, files: List[BaiduFileInfo]) -> List[BaiduFileInfo]:
        """过滤媒体文件"""
        media_files = []
        
        for file_info in files:
            if file_info.is_dir:
                continue
                
            # 根据文件扩展名判断
            file_ext = os.path.splitext(file_info.filename)[1].lower()
            is_media = (file_ext in self.video_extensions or 
                       file_ext in self.audio_extensions or
                       file_info.category in [1, 2])  # 视频/音频类别
            
            if is_media:
                media_files.append(file_info)
        
        return media_files
    
    def batch_rapid_upload(self, rapid_links: List[str], target_dir: str = "/") -> Dict[str, bool]:
        """
        批量秒传
        
        :param rapid_links: 秒传链接列表
        :param target_dir: 目标目录
        :return: 上传结果字典 {filename: success}
        """
        logger.info(f"⚡ 批量秒传: {len(rapid_links)} 个文件")
        
        results = {}
        
        for link in rapid_links:
            try:
                rapid_info = self.parse_rapid_upload_link(link)
                if not rapid_info:
                    results[link] = False
                    continue
                
                target_path = os.path.join(target_dir, rapid_info.filename).replace('\\', '/')
                success = self.rapid_upload(rapid_info, target_path)
                results[rapid_info.filename] = success
                
                # 添加延迟避免请求过快
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ 秒传失败 {link}: {e}")
                results[link] = False
        
        successful = sum(1 for success in results.values() if success)
        logger.info(f"✅ 批量秒传完成: 成功 {successful}/{len(rapid_links)} 个")
        
        return results