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
    """BaiduPCS API 下载器 - 直接使用 Python API 绕过命令行工具的 bug"""
    
    def __init__(self, api: Optional[BaiduPCSApi] = None):
        """
        初始化下载器
        
        Args:
            api: BaiduPCSApi 实例，如果为 None 则自动创建
        """
        if api is None:
            # 从配置文件自动加载
            from baidupcs_py.app.account import AccountManager
            from baidupcs_py.commands.env import ACCOUNT_DATA_PATH
            
            account_manager = AccountManager.load_data(ACCOUNT_DATA_PATH)
            account = account_manager.who()
            
            if not account:
                raise ValueError("未找到已登录的百度网盘账号，请先使用 BaiduPCS-Py 登录")
            
            # 使用 account.pcsapi() 方法创建 API 实例
            api = account.pcsapi()
        
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
            parent_dir = os.path.dirname(remote_path)
            filename = os.path.basename(remote_path)
            
            # 列出父目录
            pcs_files = self.api.list(parent_dir)
            
            # 查找文件
            for pcs_file in pcs_files:
                if pcs_file.path == remote_path or os.path.basename(pcs_file.path) == filename:
                    return {
                        'path': pcs_file.path,
                        'size': pcs_file.size,
                        'is_dir': pcs_file.is_dir,
                        'fs_id': pcs_file.fs_id,
                        'md5': pcs_file.md5,
                    }
            
            return None
        except Exception as e:
            logger.error(f"获取文件信息失败: {e}")
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
            
            # 使用 MeDownloader
            local_path_tmp = local_path + ".tmp"
            
            downloader = MeDownloader(
                "GET",
                download_link,
                headers=headers,
                max_workers=concurrency,
            )
            
            with open(local_path_tmp, "wb") as f:
                downloader.download(f, chunk_size=chunk_size)
            
            # 下载完成，重命名
            if os.path.exists(local_path_tmp):
                import shutil
                shutil.move(local_path_tmp, local_path)
                
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

