#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BaiduPCS API 下载器
直接使用 Python API，避免命令行工具的长路径问题
"""

import os
import hashlib
from typing import Optional, Dict, Any
from pathlib import Path

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.common.downloader import MeDownloader
from baidupcs_py.baidupcs import PCS_UA

import logging

logger = logging.getLogger(__name__)


class BaiduPCSDownloader:
    """BaiduPCS API 下载器 - 直接使用 Python API，完全替代命令行工具"""

    def __init__(self, api: Optional[BaiduPCSApi] = None):
        """
        初始化下载器

        Args:
            api: BaiduPCSApi 实例，如果为 None 则自动创建
        """
        from baidupcs_py.app.account import AccountManager
        from baidupcs_py.commands.env import ACCOUNT_DATA_PATH
        
        self.account_manager = AccountManager.load_data(ACCOUNT_DATA_PATH)
        
        if api is None:
            # 从配置文件自动加载
            account = self.account_manager.who()

            if account:
                # 使用 account.pcsapi() 方法创建 API 实例
                api = account.pcsapi()
            else:
                # 如果没有账号，api 为 None，某些操作会失败
                api = None

        self.api = api
    
    def file_exists(self, remote_path: str) -> bool:
        """
        检查文件是否存在
        
        使用 list 方法而不是 meta 方法，避免长路径问题
        
        Args:
            remote_path: 远程文件路径
            
        Returns:
            bool: 文件是否存在
        """
        try:
            parent_dir = os.path.dirname(remote_path)
            filename = os.path.basename(remote_path)
            
            # 列出父目录
            pcs_files = self.api.list(parent_dir)
            
            # 查找文件
            for pcs_file in pcs_files:
                if pcs_file.path == remote_path:
                    return True
                # 也尝试匹配文件名（处理空格规范化问题）
                if os.path.basename(pcs_file.path) == filename:
                    return True
            
            return False
        except Exception as e:
            logger.error(f"检查文件存在性失败: {e}")
            return False
    
    def get_file_info(self, remote_path: str) -> Optional[Dict[str, Any]]:
        """
        获取文件信息
        
        Args:
            remote_path: 远程文件路径
            
        Returns:
            文件信息字典，如果文件不存在则返回 None
        """
        try:
            import re
            
            parent_dir = os.path.dirname(remote_path)
            filename = os.path.basename(remote_path)
            
            logger.info(f"🔍 获取文件信息:")
            logger.info(f"   父目录: {parent_dir}")
            logger.info(f"   文件名: {filename}")
            
            # 列出父目录
            logger.info(f"📋 列出父目录内容...")
            pcs_files = self.api.list(parent_dir)
            logger.info(f"✅ 找到 {len(pcs_files)} 个文件/目录")
            
            # 规范化文件名中的空格
            # 策略1: 将多个空格替换为单个空格
            normalized_filename = re.sub(r'\s+', ' ', filename)
            # 策略2: 移除所有空格（用于更宽松的匹配）
            no_space_filename = re.sub(r'\s+', '', filename)
            
            # 查找文件
            for pcs_file in pcs_files:
                actual_filename = os.path.basename(pcs_file.path)
                normalized_actual = re.sub(r'\s+', ' ', actual_filename)
                no_space_actual = re.sub(r'\s+', '', actual_filename)
                
                # 先尝试精确匹配
                if pcs_file.path == remote_path or actual_filename == filename:
                    logger.info(f"✅ 精确匹配成功: {actual_filename}")
                    return {
                        'path': pcs_file.path,
                        'size': pcs_file.size,
                        'is_dir': pcs_file.is_dir,
                        'fs_id': pcs_file.fs_id,
                        'md5': pcs_file.md5,
                    }
                
                # 尝试规范化空格后匹配（多个空格 -> 单个空格）
                if normalized_actual == normalized_filename:
                    logger.info(f"🔍 通过规范化空格找到匹配文件 (多空格->单空格):")
                    logger.info(f"   请求的文件名: {repr(filename)}")
                    logger.info(f"   实际的文件名: {repr(actual_filename)}")
                    return {
                        'path': pcs_file.path,
                        'size': pcs_file.size,
                        'is_dir': pcs_file.is_dir,
                        'fs_id': pcs_file.fs_id,
                        'md5': pcs_file.md5,
                    }
                
                # 尝试移除所有空格后匹配（更宽松的匹配）
                if no_space_actual == no_space_filename:
                    logger.info(f"🔍 通过移除空格找到匹配文件 (忽略所有空格):")
                    logger.info(f"   请求的文件名: {repr(filename)}")
                    logger.info(f"   实际的文件名: {repr(actual_filename)}")
                    return {
                        'path': pcs_file.path,
                        'size': pcs_file.size,
                        'is_dir': pcs_file.is_dir,
                        'fs_id': pcs_file.fs_id,
                        'md5': pcs_file.md5,
                    }
            
            logger.warning(f"⚠️ 未找到匹配文件: {filename}")
            logger.info(f"📁 目录中的前10个文件:")
            for i, pcs_file in enumerate(pcs_files[:10]):
                logger.info(f"   [{i+1}] {os.path.basename(pcs_file.path)}")
            
            return None
        except Exception as e:
            logger.error(f"❌ 获取文件信息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def download_file(
        self,
        remote_path: str,
        local_dir: str,
        local_filename: Optional[str] = None,
        concurrency: int = 5,
        chunk_size: int = 4 * 1024 * 1024,  # 4MB
        simplify_long_filename: bool = True,
        max_filename_length: int = 100
    ) -> Dict[str, Any]:
        """
        下载文件
        
        Args:
            remote_path: 远程文件路径
            local_dir: 本地目录
            local_filename: 本地文件名（可选），如果不指定则使用远程文件名
            concurrency: 并发数
            chunk_size: 分块大小
            simplify_long_filename: 是否简化长文件名
            max_filename_length: 最大文件名长度
            
        Returns:
            下载结果字典
        """
        try:
            # 1. 检查文件是否存在
            logger.info(f"🔍 检查文件是否存在: {remote_path}")
            file_info = self.get_file_info(remote_path)
            
            if not file_info:
                return {
                    'success': False,
                    'message': f'文件不存在: {remote_path}',
                    'error_type': 'file_not_found'
                }
            
            # 更新 remote_path 为实际路径（处理空格规范化）
            actual_remote_path = file_info['path']
            logger.info(f"✅ 文件存在: {actual_remote_path}")
            logger.info(f"   文件大小: {file_info['size']} 字节")
            
            # 2. 确定本地文件名
            if not local_filename:
                original_filename = os.path.basename(actual_remote_path)
                
                # 简化长文件名
                if simplify_long_filename and len(original_filename) > max_filename_length:
                    ext = Path(original_filename).suffix
                    base_name = Path(original_filename).stem
                    
                    # 使用前50个字符 + MD5哈希
                    prefix = base_name[:50]
                    hash_value = hashlib.md5(original_filename.encode('utf-8')).hexdigest()[:8]
                    local_filename = f"{prefix}_{hash_value}{ext}"
                    
                    logger.info(f"🔧 简化文件名:")
                    logger.info(f"   原始: {original_filename}")
                    logger.info(f"   简化: {local_filename}")
                else:
                    local_filename = original_filename
            
            # 3. 确保本地目录存在
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, local_filename)
            
            # 4. 获取下载链接
            logger.info(f"🔗 获取下载链接...")
            download_link = self.api.download_link(actual_remote_path)
            
            if not download_link:
                return {
                    'success': False,
                    'message': '获取下载链接失败',
                    'error_type': 'no_download_link'
                }
            
            logger.info(f"✅ 获取下载链接成功")
            
            # 5. 使用 MeDownloader 下载
            logger.info(f"📥 开始下载文件...")
            logger.info(f"   远程路径: {actual_remote_path}")
            logger.info(f"   本地路径: {local_path}")
            logger.info(f"   并发数: {concurrency}")
            
            # 准备下载参数
            cookies = {
                'BDUSS': self.api._baidupcs._bduss
            }
            
            headers = {
                "Cookie": f"BDUSS={cookies['BDUSS']};",
                "User-Agent": PCS_UA,
                "Connection": "Keep-Alive",
            }
            
            # 使用 MeDownloader - 直接下载到最终文件名，避免重命名导致的文件锁定问题
            # 
            # 重要：MeDownloader 使用类级别的全局线程池，可能被其他下载关闭
            # 解决方案：每次下载前确保线程池已初始化
            from concurrent.futures import ThreadPoolExecutor
            from threading import Semaphore
            
            # 检查线程池是否可用，如果不可用则重新初始化
            if not hasattr(MeDownloader, '_executor') or MeDownloader._executor._shutdown:
                logger.info("🔄 重新初始化 MeDownloader 线程池")
                MeDownloader._executor = ThreadPoolExecutor(max_workers=concurrency)
                MeDownloader._semaphore = Semaphore(concurrency)
                MeDownloader._futures = []
            
            downloader = MeDownloader(
                "GET",
                download_link,
                headers=headers,
                max_workers=concurrency,
            )
            
            # MeDownloader.download() 参数: (localpath, task_id, continue_, done_callback)
            # 直接下载到最终路径，不使用 .tmp 后缀
            downloader.download(local_path, task_id=None, continue_=False)
            
            # 等待文件完全写入
            import time
            time.sleep(0.5)
            
            # 验证下载结果
            if os.path.exists(local_path):
                actual_size = os.path.getsize(local_path)
                logger.info(f"✅ 下载成功!")
                logger.info(f"   文件路径: {local_path}")
                logger.info(f"   文件大小: {actual_size} 字节")
                
                return {
                    'success': True,
                    'message': '下载成功',
                    'local_path': local_path,
                    'remote_path': actual_remote_path,
                    'file_size': actual_size
                }
            else:
                return {
                    'success': False,
                    'message': '下载失败：临时文件不存在',
                    'error_type': 'download_failed'
                }
                
        except Exception as e:
            logger.error(f"❌ 下载失败: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'success': False,
                'message': f'下载失败: {str(e)}',
                'error_type': 'exception',
                'exception': str(e)
            }
        finally:
            # 清理 MeDownloader
            MeDownloader._exit_executor()
    
    # ==================== 用户管理功能 ====================
    
    def is_authenticated(self) -> bool:
        """检查用户是否已认证"""
        try:
            if self.api is None:
                return False
            
            # 尝试获取用户信息来验证认证状态
            user_info = self.api.user_info()
            return user_info is not None
        except Exception as e:
            logger.error(f"检查认证状态失败: {e}")
            return False
    
    def add_user_by_cookies(self, cookies: str) -> Dict[str, Any]:
        """
        通过 cookies 添加用户
        
        Args:
            cookies: 百度网盘 cookies 字符串
            
        Returns:
            操作结果字典
        """
        try:
            from baidupcs_py.commands.env import ACCOUNT_DATA_PATH
            
            # 清理cookies字符串：移除多余的换行符和空格
            cookies = cookies.strip().replace('\n', ' ').replace('\r', ' ')
            
            logger.info(f"📋 原始cookies长度: {len(cookies)}")
            logger.info(f"📋 Cookies前200字符: {cookies[:200]}")
            logger.info(f"📋 Cookies后200字符: {cookies[-200:]}")
            
            # 解析 cookies 获取 BDUSS 和 STOKEN
            bduss = None
            stoken = None
            
            # 调试：显示所有cookie键
            cookie_keys = []
            for cookie in cookies.split(';'):
                cookie = cookie.strip()
                if '=' in cookie:
                    key = cookie.split('=')[0]
                    cookie_keys.append(key)
            
            logger.info(f"📋 发现的Cookie键: {', '.join(cookie_keys)}")
            
            for cookie in cookies.split(';'):
                cookie = cookie.strip()
                if cookie.startswith('BDUSS='):
                    bduss = cookie.split('=', 1)[1].strip()
                    logger.info(f"✅ 找到BDUSS，长度: {len(bduss)}")
                elif cookie.startswith('BDUSS_BFESS='):
                    # 注意：BDUSS_BFESS 不是 BDUSS，跳过
                    logger.info(f"⚠️  发现BDUSS_BFESS（这不是BDUSS）")
                elif cookie.startswith('STOKEN='):
                    stoken = cookie.split('=', 1)[1].strip()
                    logger.info(f"✅ 找到STOKEN，长度: {len(stoken)}")
            
            if not bduss:
                logger.error("❌ cookies中未找到BDUSS")
                logger.error(f"Cookies内容: {cookies[:200]}")
                return {
                    'success': False,
                    'message': 'cookies 中未找到 BDUSS。请确保cookies字符串格式正确，应包含 BDUSS=xxx 字段'
                }
            
            logger.info(f"✅ 从cookies中成功解析 - BDUSS长度: {len(bduss)}, STOKEN: {'有' if stoken else '无'}")
            
            # 使用 BDUSS 添加用户
            return self.add_user_by_bduss(bduss, stoken)
            
        except Exception as e:
            logger.error(f"通过 cookies 添加用户失败: {e}")
            return {
                'success': False,
                'message': f'添加用户失败: {str(e)}'
            }
    
    def add_user_by_bduss(self, bduss: str, stoken: str = None) -> Dict[str, Any]:
        """
        通过 BDUSS 添加用户
        
        Args:
            bduss: 百度网盘 BDUSS
            stoken: 可选的 STOKEN
            
        Returns:
            操作结果字典
        """
        try:
            from baidupcs_py.app.account import Account
            from baidupcs_py.commands.env import ACCOUNT_DATA_PATH
            
            # 清理BDUSS：移除换行符、空格等特殊字符
            original_bduss = bduss
            bduss = bduss.strip().replace('\n', '').replace('\r', '').replace(' ', '').replace('\t', '')
            
            if not bduss:
                logger.error("BDUSS清理后为空")
                return {
                    'success': False,
                    'message': 'BDUSS不能为空'
                }
            
            if len(original_bduss) != len(bduss):
                logger.info(f"清理了BDUSS中的特殊字符，原长度: {len(original_bduss)}, 清理后: {len(bduss)}")
            
            # 创建cookies字典
            cookies = {}
            if stoken:
                stoken = stoken.strip().replace('\n', '').replace('\r', '').replace(' ', '').replace('\t', '')
                cookies['STOKEN'] = stoken
            
            # 创建账号
            logger.info(f"🔧 开始创建账号，BDUSS长度: {len(bduss)}, STOKEN: {'有' if stoken else '无'}")
            logger.info(f"🔧 BDUSS前30字符: {bduss[:30]}")
            logger.info(f"🔧 BDUSS后30字符: {bduss[-30:]}")
            logger.info(f"🔧 传递给BaiduPCS-Py的cookies: {cookies}")
            
            account = Account.from_bduss(bduss, cookies=cookies)
            logger.info(f"✅ 账号创建成功，用户ID: {account.user.user_id}, 用户名: {account.user.user_name}")
            
            # 添加到账号管理器
            # 注意：先add_account，再su切换到该用户
            self.account_manager.add_account(account)
            self.account_manager.su(account.user.user_id)
            self.account_manager.save(ACCOUNT_DATA_PATH)
            
            # 更新当前 API 实例
            self.api = account.pcsapi()
            
            logger.info("✅ 用户添加成功并已保存")
            return {
                'success': True,
                'message': '用户添加成功',
                'user_id': account.user.user_id,
                'user_name': account.user.user_name
            }
            
        except Exception as e:
            logger.error(f"通过 BDUSS 添加用户失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return {
                'success': False,
                'message': f'添加用户失败: {str(e)}'
            }
    
    def get_user_info(self) -> Dict[str, Any]:
        """
        获取当前用户信息
        
        Returns:
            用户信息字典
        """
        try:
            if not self.api:
                return {
                    'success': False,
                    'message': '未登录'
                }
            
            # 获取用户信息
            user_info = self.api.user_info()
            
            if user_info:
                return {
                    'success': True,
                    'user_id': user_info.user_id,
                    'user_name': user_info.user_name,
                    'quota': getattr(user_info, 'quota', 0),
                    'used': getattr(user_info, 'used', 0)
                }
            else:
                return {
                    'success': False,
                    'message': '获取用户信息失败'
                }
                
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return {
                'success': False,
                'message': f'获取用户信息失败: {str(e)}'
            }
    
    # ==================== 文件操作功能 ====================
    
    def list_files(self, path: str = "/", recursive: bool = False) -> Dict[str, Any]:
        """
        列出文件
        
        Args:
            path: 远程路径
            recursive: 是否递归列出子目录
            
        Returns:
            文件列表字典
        """
        try:
            if not self.api:
                return {
                    'success': False,
                    'message': '未登录'
                }
            
            # 列出文件
            pcs_files = self.api.list(path)
            
            # 定义媒体文件扩展名
            video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.m2ts', '.f4v', '.rmvb', '.rm'}
            audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.ape', '.ac3', '.dts'}
            
            files = []
            for pcs_file in pcs_files:
                filename = os.path.basename(pcs_file.path)
                file_ext = os.path.splitext(filename)[1].lower()
                
                # 判断是否为媒体文件
                is_media = (file_ext in video_extensions or file_ext in audio_extensions) and not pcs_file.is_dir
                
                file_info = {
                    'path': pcs_file.path,
                    'filename': filename,
                    'is_dir': pcs_file.is_dir,
                    'is_media': is_media,
                    'size': pcs_file.size,
                    'fs_id': pcs_file.fs_id,
                    'md5': pcs_file.md5,
                    'server_mtime': pcs_file.server_mtime
                }
                files.append(file_info)
                
                # 如果是目录且需要递归
                if recursive and pcs_file.is_dir:
                    sub_result = self.list_files(pcs_file.path, recursive=True)
                    if sub_result.get('success'):
                        files.extend(sub_result.get('files', []))
            
            return {
                'success': True,
                'files': files,
                'count': len(files)
            }
            
        except Exception as e:
            logger.error(f"列出文件失败: {e}")
            return {
                'success': False,
                'message': f'列出文件失败: {str(e)}'
            }
    
    def upload_file(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        """
        上传文件
        
        Args:
            local_path: 本地文件路径
            remote_path: 远程文件路径
            
        Returns:
            上传结果字典
        """
        try:
            if not self.api:
                return {
                    'success': False,
                    'message': '未登录'
                }
            
            if not os.path.exists(local_path):
                return {
                    'success': False,
                    'message': f'本地文件不存在: {local_path}'
                }
            
            # 上传文件
            from baidupcs_py.commands.upload import upload as pcs_upload
            
            pcs_upload(
                self.api,
                local_path,
                remote_path,
                ondup='overwrite'  # 覆盖同名文件
            )
            
            logger.info(f"✅ 文件上传成功: {remote_path}")
            return {
                'success': True,
                'message': '上传成功',
                'remote_path': remote_path
            }
            
        except Exception as e:
            logger.error(f"上传文件失败: {e}")
            return {
                'success': False,
                'message': f'上传文件失败: {str(e)}'
            }


def create_downloader() -> BaiduPCSDownloader:
    """创建下载器实例"""
    return BaiduPCSDownloader()


if __name__ == "__main__":
    # 测试代码
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    if len(sys.argv) < 3:
        print("用法: python baidupcs_downloader_fixed.py <远程路径> <本地目录>")
        sys.exit(1)
    
    remote_path = sys.argv[1]
    local_dir = sys.argv[2]
    
    downloader = create_downloader()
    result = downloader.download_file(remote_path, local_dir)
    
    print(f"\n下载结果: {result}")

