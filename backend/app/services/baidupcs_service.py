#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BaiduPCS-Py 服务
提供百度网盘文件操作功能
"""

import os
import json
import time
import tempfile
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import subprocess

from baidupcs_py import BaiduPCS
from app.utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class BaiduPCSUser:
    """BaiduPCS用户信息"""
    user_name: str
    cookies: str
    bduss: Optional[str] = None
    user_id: Optional[int] = None
    quota_used: Optional[int] = None
    quota_total: Optional[int] = None
    quota_used_readable: Optional[str] = None
    quota_total_readable: Optional[str] = None
    is_default: bool = False
    is_active: bool = False

@dataclass
class BaiduPCSFile:
    """BaiduPCS文件信息"""
    fs_id: str
    filename: str
    path: str
    is_dir: bool
    is_media: bool
    size: int
    size_readable: str
    ctime: int
    mtime: int

class BaiduPCSService:
    """BaiduPCS服务类"""
    
    def __init__(self):
        self.users_file = Path("data/baidupcs_users.json")
        self.users_file.parent.mkdir(exist_ok=True)
        self._current_user: Optional[BaiduPCSUser] = None
        self._baidupcs_instance: Optional[BaiduPCS] = None
        self._load_users()
    
    def _load_users(self):
        """加载用户列表"""
        try:
            if self.users_file.exists():
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    users_data = data.get('users', [])
                    self._users = [BaiduPCSUser(**user) for user in users_data]
                    
                    # 找到默认用户
                    for user in self._users:
                        if user.is_default:
                            self._current_user = user
                            self._init_baidupcs(user)
                            break
            else:
                self._users = []
        except Exception as e:
            logger.error(f"加载用户列表失败: {e}")
            self._users = []
    
    def _save_users(self):
        """保存用户列表"""
        try:
            data = {
                'users': [
                    {
                        'user_name': user.user_name,
                        'cookies': user.cookies,
                        'bduss': user.bduss,
                        'user_id': user.user_id,
                        'quota_used': user.quota_used,
                        'quota_total': user.quota_total,
                        'quota_used_readable': user.quota_used_readable,
                        'quota_total_readable': user.quota_total_readable,
                        'is_default': user.is_default,
                        'is_active': user.is_active
                    }
                    for user in self._users
                ]
            }
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存用户列表失败: {e}")
    
    def _init_baidupcs(self, user: BaiduPCSUser) -> bool:
        """初始化BaiduPCS实例"""
        try:
            # 解析cookies
            cookies_dict = {}
            if user.cookies:
                for cookie_pair in user.cookies.split(';'):
                    if '=' in cookie_pair:
                        name, value = cookie_pair.split('=', 1)
                        name = name.strip()
                        value = value.strip()
                        if name and value:
                            cookies_dict[name] = value
            
            # 创建BaiduPCS实例
            self._baidupcs_instance = BaiduPCS(cookies=cookies_dict)
            
            # 验证并获取用户信息
            try:
                user_info = self._baidupcs_instance.user_info()
                quota_info = self._baidupcs_instance.quota()
                
                user.user_id = user_info.get('uk')
                user.quota_used = quota_info.get('used', 0)
                user.quota_total = quota_info.get('total', 0)
                user.quota_used_readable = self._format_size(user.quota_used)
                user.quota_total_readable = self._format_size(user.quota_total)
                user.is_active = True
                
                logger.info(f"✅ BaiduPCS用户 {user.user_name} 认证成功")
                return True
                
            except Exception as e:
                logger.warning(f"⚠️ BaiduPCS用户 {user.user_name} 认证失败: {e}")
                user.is_active = False
                return False
                
        except Exception as e:
            logger.error(f"❌ 初始化BaiduPCS失败: {e}")
            return False
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def add_user(self, user_name: str = None, cookies: str = None, bduss: str = None) -> Dict[str, Any]:
        """添加用户"""
        try:
            if not cookies and not bduss:
                return {"success": False, "message": "必须提供cookies或bduss"}
            
            # 如果没有提供user_name，生成一个
            if not user_name:
                user_name = f"user_{int(time.time())}"
            
            # 检查用户是否已存在
            for user in self._users:
                if user.user_name == user_name:
                    return {"success": False, "message": f"用户 {user_name} 已存在"}
            
            # 创建新用户
            new_user = BaiduPCSUser(
                user_name=user_name,
                cookies=cookies or "",
                bduss=bduss
            )
            
            # 如果没有其他用户，设为默认用户
            if not self._users:
                new_user.is_default = True
            
            # 初始化BaiduPCS
            if self._init_baidupcs(new_user):
                self._users.append(new_user)
                
                # 如果这是第一个用户或设为默认用户，更新当前用户
                if new_user.is_default:
                    self._current_user = new_user
                
                self._save_users()
                
                return {
                    "success": True,
                    "message": f"用户 {user_name} 添加成功",
                    "user": {
                        "user_name": new_user.user_name,
                        "user_id": new_user.user_id,
                        "quota_used_readable": new_user.quota_used_readable,
                        "quota_total_readable": new_user.quota_total_readable
                    }
                }
            else:
                return {"success": False, "message": "用户认证失败，请检查cookies或bduss"}
                
        except Exception as e:
            logger.error(f"❌ 添加用户失败: {e}")
            return {"success": False, "message": f"添加用户失败: {str(e)}"}
    
    def remove_user(self, user_name: str = None, user_id: int = None) -> Dict[str, Any]:
        """删除用户"""
        try:
            # 找到要删除的用户
            user_to_remove = None
            for user in self._users:
                if (user_name and user.user_name == user_name) or \
                   (user_id and user.user_id == user_id):
                    user_to_remove = user
                    break
            
            if not user_to_remove:
                return {"success": False, "message": "用户不存在"}
            
            # 删除用户
            self._users.remove(user_to_remove)
            
            # 如果删除的是当前用户，切换到下一个用户
            if self._current_user == user_to_remove:
                if self._users:
                    self._current_user = self._users[0]
                    self._current_user.is_default = True
                    self._init_baidupcs(self._current_user)
                else:
                    self._current_user = None
                    self._baidupcs_instance = None
            
            self._save_users()
            
            return {
                "success": True,
                "message": f"用户 {user_to_remove.user_name} 删除成功"
            }
            
        except Exception as e:
            logger.error(f"❌ 删除用户失败: {e}")
            return {"success": False, "message": f"删除用户失败: {str(e)}"}
    
    def get_users(self) -> List[Dict[str, Any]]:
        """获取用户列表"""
        return [
            {
                "user_name": user.user_name,
                "user_id": user.user_id,
                "quota_used": user.quota_used,
                "quota_total": user.quota_total,
                "quota_used_readable": user.quota_used_readable,
                "quota_total_readable": user.quota_total_readable,
                "is_default": user.is_default,
                "is_active": user.is_active
            }
            for user in self._users
        ]
    
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return self._current_user is not None and self._current_user.is_active
    
    def get_current_user_info(self) -> Optional[Dict[str, Any]]:
        """获取当前用户信息"""
        if not self._current_user:
            return None
        
        return {
            "user_name": self._current_user.user_name,
            "user_id": self._current_user.user_id,
            "quota_used": self._current_user.quota_used,
            "quota_total": self._current_user.quota_total,
            "quota_used_readable": self._current_user.quota_used_readable,
            "quota_total_readable": self._current_user.quota_total_readable,
            "is_default": self._current_user.is_default,
            "is_active": self._current_user.is_active
        }
    
    def get_file_list(self, path: str = "/", user_name: str = None) -> Dict[str, Any]:
        """获取文件列表"""
        try:
            if not self.is_authenticated():
                return {"success": False, "message": "未认证或用户未激活"}
            
            # 如果指定了用户名，切换用户
            if user_name and user_name != self._current_user.user_name:
                for user in self._users:
                    if user.user_name == user_name and user.is_active:
                        self._current_user = user
                        self._init_baidupcs(user)
                        break
                else:
                    return {"success": False, "message": f"用户 {user_name} 不存在或未激活"}
            
            # 获取文件列表
            response = self._baidupcs_instance.list(path)
            
            files = []
            media_count = 0
            
            logger.debug(f"🔍 BaiduPCS list() 响应类型: {type(response)}")
            logger.debug(f"🔍 BaiduPCS list() 响应内容: {response}")
            
            # 检查响应格式
            files_data = []
            
            if hasattr(response, 'list'):
                # 检查list是方法还是属性
                if callable(response.list):
                    # 如果是方法，调用它
                    files_data = response.list()
                    logger.info(f"📂 调用响应.list()获取到 {len(files_data) if hasattr(files_data, '__len__') else 'N/A'} 个文件")
                else:
                    # 如果是属性，直接使用
                    files_data = response.list
                    logger.info(f"📂 从响应.list获取到 {len(files_data) if hasattr(files_data, '__len__') else 'N/A'} 个文件")
            elif isinstance(response, list):
                # 如果response本身就是列表
                files_data = response
                logger.info(f"📂 响应本身是列表，包含 {len(files_data)} 个文件")
            else:
                # 尝试其他可能的属性名
                for attr_name in ['files', 'entries', 'items', 'data']:
                    if hasattr(response, attr_name):
                        attr_value = getattr(response, attr_name)
                        if callable(attr_value):
                            # 如果是方法，调用它并处理可能的键值对格式
                            result = attr_value()
                            if hasattr(result, '__iter__') and not isinstance(result, (str, bytes)):
                                # 检查是否为键值对迭代器
                                try:
                                    items_list = list(result)
                                    logger.debug(f"🔍 {attr_name}()返回项目: {len(items_list)} 个")
                                    
                                    # 查找 'list' 键
                                    for item in items_list:
                                        if isinstance(item, tuple) and len(item) == 2:
                                            key, value = item
                                            logger.debug(f"🔍 发现键值对: {key}")
                                            if key == 'list' and isinstance(value, list):
                                                files_data = value
                                                logger.info(f"📂 从键值对 {key} 获取到 {len(files_data)} 个文件")
                                                break
                                    
                                    if not files_data:
                                        # 如果没找到'list'键，尝试第一个列表值
                                        for item in items_list:
                                            if isinstance(item, tuple) and len(item) == 2:
                                                key, value = item
                                                if isinstance(value, list):
                                                    files_data = value
                                                    logger.info(f"📂 从键值对 {key} 获取到 {len(files_data)} 个文件")
                                                    break
                                except Exception as e:
                                    logger.error(f"❌ 解析 {attr_name}() 结果失败: {e}")
                                    files_data = result if isinstance(result, list) else []
                            else:
                                files_data = result if isinstance(result, list) else []
                                logger.info(f"📂 调用响应.{attr_name}()获取到 {len(files_data) if hasattr(files_data, '__len__') else 'N/A'} 个文件")
                        else:
                            files_data = attr_value if isinstance(attr_value, list) else []
                            logger.info(f"📂 从响应.{attr_name}获取到 {len(files_data)} 个文件")
                        
                        if files_data:
                            break
                
                if not files_data:
                    logger.warning(f"⚠️ 无法从响应中找到文件列表")
                    logger.debug(f"🔍 响应可用属性: {[attr for attr in dir(response) if not attr.startswith('_')]}")
            
            for i, file_info in enumerate(files_data):
                try:
                    logger.debug(f"🗂️ 文件 {i}: {type(file_info)}")
                    
                    # 处理字典格式的文件信息
                    if isinstance(file_info, dict):
                        # 从字典中提取文件信息
                        fs_id = str(file_info.get('fs_id', 'unknown'))
                        filename = file_info.get('server_filename') or file_info.get('filename', '未知文件')
                        is_dir = file_info.get('isdir', 0) == 1
                        file_path = file_info.get('path', f"{path.rstrip('/')}/{filename}")
                        size = file_info.get('size', 0)
                        ctime = file_info.get('server_ctime') or file_info.get('ctime', 0)
                        mtime = file_info.get('server_mtime') or file_info.get('mtime', 0)
                        
                        is_media = self._is_media_file(filename) if not is_dir else False
                        if is_media:
                            media_count += 1
                        
                        files.append(BaiduPCSFile(
                            fs_id=fs_id,
                            filename=filename,
                            path=file_path,
                            is_dir=is_dir,
                            is_media=is_media,
                            size=size,
                            size_readable=self._format_size(size),
                            ctime=ctime,
                            mtime=mtime
                        ))
                        
                        logger.debug(f"✅ 解析文件成功: {filename} ({'目录' if is_dir else '文件'})")
                        
                    # 检查file_info的类型和属性（对象格式）
                    elif hasattr(file_info, 'is_dir') and hasattr(file_info, 'filename'):
                        is_media = self._is_media_file(file_info.filename) if not file_info.is_dir else False
                        if is_media:
                            media_count += 1
                        
                        files.append(BaiduPCSFile(
                            fs_id=str(getattr(file_info, 'fs_id', 'unknown')),
                            filename=file_info.filename,
                            path=getattr(file_info, 'path', f"{path.rstrip('/')}/{file_info.filename}"),
                            is_dir=file_info.is_dir,
                            is_media=is_media,
                            size=getattr(file_info, 'size', 0),
                            size_readable=self._format_size(getattr(file_info, 'size', 0)),
                            ctime=getattr(file_info, 'ctime', 0),
                            mtime=getattr(file_info, 'mtime', 0)
                        ))
                    elif hasattr(file_info, 'server_filename'):
                        # 尝试API格式的文件信息（对象格式）
                        is_dir = getattr(file_info, 'isdir', 0) == 1
                        filename = file_info.server_filename
                        is_media = self._is_media_file(filename) if not is_dir else False
                        if is_media:
                            media_count += 1
                        
                        files.append(BaiduPCSFile(
                            fs_id=str(getattr(file_info, 'fs_id', 'unknown')),
                            filename=filename,
                            path=getattr(file_info, 'path', f"{path.rstrip('/')}/{filename}"),
                            is_dir=is_dir,
                            is_media=is_media,
                            size=getattr(file_info, 'size', 0),
                            size_readable=self._format_size(getattr(file_info, 'size', 0)),
                            ctime=getattr(file_info, 'server_ctime', 0),
                            mtime=getattr(file_info, 'server_mtime', 0)
                        ))
                    else:
                        logger.warning(f"⚠️ 无法解析文件对象: {type(file_info)} - {file_info}")
                        
                except Exception as e:
                    logger.error(f"❌ 处理文件 {i} 失败: {e}")
                    logger.debug(f"🔍 文件信息详情: {file_info}")
                    continue
            
            return {
                "success": True,
                "files": [
                    {
                        "fs_id": f.fs_id,
                        "filename": f.filename,
                        "path": f.path,
                        "is_dir": f.is_dir,
                        "is_media": f.is_media,
                        "size": f.size,
                        "size_readable": f.size_readable,
                        "ctime": f.ctime,
                        "mtime": f.mtime
                    }
                    for f in files
                ],
                "media_count": media_count,
                "total_count": len(files),
                "current_path": path
            }
            
        except Exception as e:
            logger.error(f"❌ 获取文件列表失败: {e}")
            return {"success": False, "message": f"获取文件列表失败: {str(e)}"}
    
    def download_file(self, remote_path: str, local_path: str, 
                     downloader: str = "me", chunk_size: str = "1M", 
                     concurrency: int = 5) -> Dict[str, Any]:
        """
        下载文件
        
        Args:
            remote_path: 远程文件路径
            local_path: 本地保存路径
            downloader: 下载器类型 (me/aget_py/aget_rs/aria2)
            chunk_size: 分块大小
            concurrency: 并发数
            
        Returns:
            Dict: 下载结果
        """
        try:
            if not self.is_authenticated():
                return {"success": False, "message": "未认证或用户未激活"}
            
            logger.info(f"📥 开始下载文件: {remote_path} -> {local_path}")
            
            # 确保本地目录存在
            local_dir = os.path.dirname(local_path)
            if local_dir:
                os.makedirs(local_dir, exist_ok=True)
            
            # 方法1: 优先尝试直接API下载
            logger.info(f"🔄 尝试方法1: 直接API下载")
            direct_result = self.download_file_direct(remote_path, local_path)
            if direct_result.get("success"):
                return direct_result
            
            logger.warning(f"⚠️ 直接API下载失败: {direct_result.get('message')}")
            
            # 方法2: 使用命令行方式调用BaiduPCS-Py（作为备用方案）
            try:
                logger.info(f"🔄 尝试方法2: 使用命令行方式下载")
                
                # 首先确保BaiduPCS-Py有当前用户
                if not self._ensure_baidupcs_user():
                    logger.error(f"❌ 无法同步用户到BaiduPCS-Py")
                    return {"success": False, "message": "无法同步用户到BaiduPCS-Py"}
                
                # 构建下载命令 - 使用正确的BaiduPCS-Py命令
                cmd = [
                    "BaiduPCS-Py",  # 直接使用BaiduPCS-Py命令
                    "download", remote_path,
                    "-o", local_dir,
                    "--downloader", downloader,
                    "--concurrency", str(concurrency),
                    "--chunk-size", chunk_size,
                    "--quiet"
                ]
                
                logger.info(f"🚀 执行命令: {' '.join(cmd)}")
                
                # 执行下载命令
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5分钟超时
                )
                
                if result.returncode == 0:
                    # 检查文件是否下载成功
                    expected_path = os.path.join(local_dir, os.path.basename(remote_path))
                    if os.path.exists(expected_path):
                        # 如果下载的文件名与目标不同，重命名
                        if expected_path != local_path:
                            import shutil
                            shutil.move(expected_path, local_path)
                        
                        file_size = os.path.getsize(local_path)
                        logger.info(f"✅ 命令行下载成功: {local_path} ({self._format_size(file_size)})")
                        return {
                            "success": True,
                            "message": "下载成功",
                            "local_path": local_path,
                            "size": file_size
                        }
                    else:
                        logger.error(f"❌ 下载完成但文件不存在: {expected_path}")
                        return {"success": False, "message": f"下载完成但文件不存在: {expected_path}"}
                else:
                    error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
                    logger.error(f"❌ 命令行下载失败: {error_msg}")
                    return {"success": False, "message": f"命令行下载失败: {error_msg}"}
                    
            except subprocess.TimeoutExpired:
                logger.error(f"❌ 下载超时")
                return {"success": False, "message": "下载超时"}
            except Exception as cmd_error:
                logger.error(f"❌ 命令行下载异常: {str(cmd_error)}")
                return {"success": False, "message": f"命令行下载异常: {str(cmd_error)}"}
            
        except Exception as e:
            logger.error(f"❌ 下载失败: {str(e)}")
            return {"success": False, "message": f"下载失败: {str(e)}"}
    
    def download_file_direct(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        """
        直接使用Python API下载文件
        
        Args:
            remote_path: 远程文件路径
            local_path: 本地保存路径
            
        Returns:
            Dict: 下载结果
        """
        try:
            if not self.is_authenticated():
                return {"success": False, "message": "未认证或用户未激活"}
            
            logger.info(f"📥 开始直接下载文件: {remote_path} -> {local_path}")
            
            # 确保本地目录存在
            local_dir = os.path.dirname(local_path)
            if local_dir:
                os.makedirs(local_dir, exist_ok=True)
            
            # 获取文件信息
            try:
                file_info = self._baidupcs_instance.meta(remote_path)
                logger.info(f"🔍 文件信息类型: {type(file_info)}")
                logger.info(f"🔍 文件信息内容: {file_info}")
                
                if not file_info:
                    return {"success": False, "message": "文件不存在"}
                
                # 处理不同的文件信息格式
                file_size = None
                if isinstance(file_info, dict):
                    # 如果是字典格式，可能包含list字段
                    if 'list' in file_info and isinstance(file_info['list'], list) and len(file_info['list']) > 0:
                        # BaiduPCS-Py返回的格式：{'list': [文件信息], 'request_id': xxx}
                        actual_file_info = file_info['list'][0]
                        file_size = actual_file_info.get('size')
                        logger.info(f"📊 从list中获取文件大小: {self._format_size(file_size) if file_size else 'N/A'}")
                    else:
                        # 直接从字典获取
                        file_size = file_info.get('size') or file_info.get('file_size')
                elif hasattr(file_info, 'size'):
                    # 如果是对象格式
                    file_size = file_info.size
                else:
                    # 尝试其他可能的属性
                    for attr in ['size', 'file_size', 'length']:
                        if hasattr(file_info, attr):
                            file_size = getattr(file_info, attr)
                            break
                
                if file_size is None:
                    logger.warning(f"⚠️ 无法获取文件大小，尝试继续下载")
                    file_size = 0
                else:
                    logger.info(f"📊 文件大小: {self._format_size(file_size)}")
                
            except Exception as meta_error:
                logger.warning(f"⚠️ 获取文件信息失败: {str(meta_error)}，尝试继续下载")
                file_size = 0
            
            # 获取下载链接
            try:
                logger.info(f"🔗 正在获取下载链接...")
                download_link = self._baidupcs_instance.download_link(remote_path)
                
                if not download_link:
                    return {"success": False, "message": "无法获取下载链接"}
                
                logger.info(f"✅ 成功获取下载链接")
                
                # 使用requests下载文件
                import requests
                
                headers = {
                    "User-Agent": "netdisk;2.2.51.6;netdisk;10.0.63;PC;android-android",
                    "Referer": "https://pan.baidu.com/",
                }
                
                logger.info(f"🌐 开始下载文件")
                
                response = requests.get(download_link, headers=headers, stream=True, timeout=60)
                response.raise_for_status()
                
                # 写入文件
                downloaded_size = 0
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                
                # 验证文件大小 (如果能获取到原始大小)
                if file_size > 0 and downloaded_size != file_size:
                    logger.warning(f"⚠️ 文件大小不匹配: 期望 {file_size}, 实际 {downloaded_size}")
                
                logger.info(f"✅ 文件下载成功: {local_path} ({self._format_size(downloaded_size)})")
                return {
                    "success": True,
                    "message": "下载成功",
                    "local_path": local_path,
                    "size": downloaded_size
                }
                
            except Exception as download_error:
                logger.error(f"❌ 下载过程出错: {str(download_error)}")
                return {"success": False, "message": f"下载过程出错: {str(download_error)}"}
            
        except Exception as e:
            logger.error(f"❌ 直接下载失败: {str(e)}")
            return {"success": False, "message": f"直接下载失败: {str(e)}"}
    
    def download_with_baidupcs_py(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        """
        使用BaiduPCS-Py命令行工具下载文件
        
        Args:
            remote_path: 远程文件路径
            local_path: 本地保存路径
            
        Returns:
            Dict: 下载结果
        """
        try:
            import subprocess
            import sys
            import os
            
            logger.info(f"🖥️ 使用BaiduPCS-Py命令行下载: {remote_path}")
            
            # 确保本地目录存在
            local_dir = os.path.dirname(local_path)
            if local_dir:
                os.makedirs(local_dir, exist_ok=True)
            
            # 构建下载命令
            cmd = [
                sys.executable, "-c",
                f"""
import sys
sys.path.insert(0, '.')
from baidupcs_py import BaiduPCSApi
from baidupcs_py.baidupcs import BaiduPCS

# 使用当前用户的认证信息
try:
    api = BaiduPCSApi(bduss='{self._current_user.bduss}', cookies='{self._current_user.cookies}')
    pcs = BaiduPCS(api)
    
    # 下载文件
    pcs.download(remotepaths=['{remote_path}'], outdir='{local_dir}')
    print("下载完成")
    
except Exception as e:
    print(f"下载失败: {{e}}")
    raise
"""
            ]
            
            # 执行下载
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            if result.returncode == 0:
                # 检查文件是否存在
                expected_path = os.path.join(local_dir, os.path.basename(remote_path))
                if os.path.exists(expected_path):
                    # 如果需要重命名
                    if expected_path != local_path:
                        import shutil
                        shutil.move(expected_path, local_path)
                    
                    file_size = os.path.getsize(local_path)
                    logger.info(f"✅ BaiduPCS-Py下载成功: {local_path} ({self._format_size(file_size)})")
                    
                    return {
                        "success": True,
                        "message": "下载成功",
                        "local_path": local_path,
                        "size": file_size
                    }
                else:
                    logger.error(f"❌ 下载完成但文件不存在: {expected_path}")
                    return {"success": False, "message": "下载完成但文件不存在"}
            else:
                error_msg = result.stderr.strip() if result.stderr else "未知错误"
                logger.error(f"❌ BaiduPCS-Py下载失败: {error_msg}")
                return {"success": False, "message": f"下载失败: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ BaiduPCS-Py命令行下载失败: {e}")
            return {"success": False, "message": f"下载失败: {str(e)}"}

    def download_with_requests(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        """
        使用requests直接下载（需要先获取下载链接）
        
        Args:
            remote_path: 远程文件路径
            local_path: 本地保存路径
            
        Returns:
            Dict: 下载结果
        """
        try:
            logger.info(f"🌐 使用requests下载: {remote_path}")
            
            # 这里需要实现获取下载链接的逻辑
            # 由于百度网盘的下载链接获取比较复杂，暂时返回不支持
            return {
                "success": False,
                "message": "requests下载方式暂未实现，请使用其他下载方式"
            }
            
        except Exception as e:
            logger.error(f"❌ requests下载失败: {e}")
            return {"success": False, "message": f"下载失败: {str(e)}"}
    
    def upload_file(self, local_path: str, remote_path: str, 
                   overwrite: bool = False) -> Dict[str, Any]:
        """
        上传文件
        
        Args:
            local_path: 本地文件路径
            remote_path: 远程目录路径
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            Dict: 上传结果
        """
        try:
            if not self.is_authenticated():
                return {"success": False, "message": "未认证或用户未激活"}
            
            if not os.path.exists(local_path):
                return {"success": False, "message": "本地文件不存在"}
            
            logger.info(f"📤 开始上传文件: {local_path} -> {remote_path}")
            
            # 使用BaiduPCS-Py的上传功能
            try:
                if hasattr(self._baidupcs_instance, 'upload'):
                    result = self._baidupcs_instance.upload(
                        localpaths=[local_path],
                        remotedir=remote_path,
                        no_ignore_existing=overwrite
                    )
                    
                    logger.info(f"✅ 上传完成: {remote_path}")
                    return {
                        "success": True,
                        "message": "上传成功",
                        "remote_path": remote_path
                    }
                else:
                    return {"success": False, "message": "BaiduPCS实例不支持上传操作"}
                    
            except Exception as upload_error:
                logger.error(f"❌ 上传失败: {upload_error}")
                return {"success": False, "message": f"上传失败: {str(upload_error)}"}
                
        except Exception as e:
            logger.error(f"❌ 上传文件失败: {e}")
            return {"success": False, "message": f"上传文件失败: {str(e)}"}
    
    def _is_media_file(self, filename: str) -> bool:
        """判断是否为媒体文件"""
        media_extensions = {
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
            '.mp3', '.wav', '.flac', '.aac', '.wma', '.ogg', '.m4a'
        }
        ext = Path(filename).suffix.lower()
        return ext in media_extensions 

    def _ensure_baidupcs_user(self) -> bool:
        """
        确保BaiduPCS-Py有可用的用户
        """
        try:
            logger.info(f"📋 检查BaiduPCS-Py用户状态")
            
            # 首先检查当前用户状态
            check_cmd = ["BaiduPCS-Py", "who"]
            check_result = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if check_result.returncode == 0:
                logger.info(f"✅ BaiduPCS-Py已有当前用户")
                return True
            
            logger.info(f"📝 BaiduPCS-Py没有当前用户，开始添加用户")
            
            # 检查是否有当前用户
            if not self._current_user:
                logger.error(f"❌ 没有当前用户信息")
                return False
            
            cookies = self._current_user.cookies
            if not cookies:
                logger.error(f"❌ 当前用户没有cookies信息")
                return False
            
            # 尝试添加用户到BaiduPCS-Py
            logger.info(f"➕ 正在添加用户到BaiduPCS-Py: {self._current_user.user_name}")
            
            # 使用交互式方式添加用户，直接传递cookies
            add_cmd = ["BaiduPCS-Py", "useradd", "--cookies", cookies]
            
            if self._current_user.bduss:
                add_cmd.extend(["--bduss", self._current_user.bduss])
            
            logger.info(f"🚀 执行命令: {' '.join(add_cmd[:3])} [cookies] [bduss]")
            
            add_result = subprocess.run(
                add_cmd,
                capture_output=True,
                text=True,
                timeout=60,  # 增加超时时间
                input="y\n"  # 如果有确认提示，自动确认
            )
            
            if add_result.returncode == 0:
                logger.info(f"✅ 用户添加到BaiduPCS-Py成功")
                
                # 再次检查用户状态
                final_check = subprocess.run(
                    ["BaiduPCS-Py", "who"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if final_check.returncode == 0:
                    logger.info(f"✅ BaiduPCS-Py用户验证成功")
                    return True
                else:
                    logger.warning(f"⚠️ 用户添加成功但验证失败")
                    return False
            else:
                logger.error(f"❌ 添加用户到BaiduPCS-Py失败: {add_result.stderr}")
                
                # 如果添加失败，尝试列出用户并选择第一个
                logger.info(f"🔄 尝试使用现有用户")
                userlist_result = subprocess.run(
                    ["BaiduPCS-Py", "userlist"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if userlist_result.returncode == 0 and userlist_result.stdout.strip():
                    logger.info(f"📋 找到现有用户列表")
                    # 尝试切换到第一个用户
                    su_result = subprocess.run(
                        ["BaiduPCS-Py", "su", "1"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if su_result.returncode == 0:
                        logger.info(f"✅ 切换到现有用户成功")
                        return True
                
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"❌ BaiduPCS-Py用户管理操作超时")
            return False
        except Exception as e:
            logger.error(f"❌ BaiduPCS-Py用户管理操作异常: {str(e)}")
            return False 