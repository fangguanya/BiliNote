#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BaiduPCS-Py 统一服务
完全基于BaiduPCS-Py命令行工具，使用正确的参数
"""

import os
import json
import time
import subprocess
import shutil
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

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
    """BaiduPCS统一服务类 - 使用正确的命令行参数"""
    
    def __init__(self):
        self._check_baidupcs_command()
        # 支持的媒体文件扩展名
        self.video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.m2ts', '.f4v', '.rmvb', '.rm'}
        self.audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.ape', '.ac3', '.dts'}
    
    def _check_baidupcs_command(self) -> bool:
        """检查BaiduPCS-Py命令是否可用"""
        try:
            logger.info("🔍 检查BaiduPCS-Py命令行工具...")
            result = subprocess.run(['BaiduPCS-Py', '--version'], 
                                 capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version_info = result.stdout.strip()
                logger.info(f"✅ BaiduPCS-Py命令行工具可用: {version_info}")
                return True
            else:
                logger.error(f"❌ BaiduPCS-Py命令执行失败，返回码: {result.returncode}")
                logger.error(f"错误输出: {result.stderr}")
                return False
        except FileNotFoundError:
            logger.error("❌ BaiduPCS-Py命令未找到，请确保已安装并在PATH中")
            logger.error("💡 安装方法: pip install BaiduPCS-Py")
            return False
        except subprocess.TimeoutExpired:
            logger.error("❌ BaiduPCS-Py命令检查超时")
            return False
        except Exception as e:
            logger.error(f"❌ BaiduPCS-Py命令检查异常: {e}")
            return False
    
    def _run_baidupcs_command(self, cmd_args: List[str], timeout: int = 300) -> Tuple[bool, str, str]:
        """运行BaiduPCS-Py命令"""
        try:
            cmd = ['BaiduPCS-Py'] + cmd_args
            logger.info(f"🔧 执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8'
            )
            
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            success = result.returncode == 0
            
            # 对于某些命令，即使返回码非0也可能是正常的（如who命令）
            # 记录详细信息而不仅仅是成功失败
            logger.debug(f"📋 命令执行完成:")
            logger.debug(f"   返回码: {result.returncode}")
            logger.debug(f"   标准输出长度: {len(stdout)} 字符")
            logger.debug(f"   错误输出长度: {len(stderr)} 字符")
            
            if stdout:
                logger.debug(f"   标准输出前100字符: {stdout[:100]}...")
            if stderr:
                logger.debug(f"   错误输出: {stderr}")
            
            # 对于特定命令，调整成功判断逻辑
            command_name = cmd_args[0] if cmd_args else ""
            if command_name == "who":
                # who命令：有用户信息就算成功
                has_user_info = any(keyword in stdout.lower() for keyword in ["user id:", "user name:", "bduss:"])
                if has_user_info:
                    logger.info("✅ who命令执行成功（检测到用户信息）")
                    success = True
                else:
                    logger.warning("⚠️ who命令无用户信息")
            else:
                # 其他命令：按返回码判断
                if success:
                    logger.info("✅ 命令执行成功")
                else:
                    logger.error(f"❌ 命令执行失败 (返回码: {result.returncode})")
            
            return success, stdout, stderr
            
        except subprocess.TimeoutExpired:
            logger.error(f"❌ 命令执行超时 ({timeout}秒)")
            return False, "", "命令执行超时"
        except Exception as e:
            logger.error(f"❌ 运行命令失败: {e}")
            return False, "", str(e)
    
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
    
    def _parse_user_info(self, raw_info: str) -> Dict[str, Any]:
        """解析BaiduPCS-Py的原始用户信息输出"""
        try:
            import re
            
            parsed_info = {}
            
            # 解析用户ID
            user_id_match = re.search(r'user id:\s*(\d+)', raw_info)
            if user_id_match:
                parsed_info['user_id'] = int(user_id_match.group(1))
            
            # 解析用户名
            user_name_match = re.search(r'user name:\s*(.+)', raw_info)
            if user_name_match:
                parsed_info['user_name'] = user_name_match.group(1).strip()
            
            # 解析配额信息 - 格式如: "quota: 6.7 TB/16.1 TB"
            quota_match = re.search(r'quota:\s*([\d.]+)\s*([A-Z]+)\s*/\s*([\d.]+)\s*([A-Z]+)', raw_info)
            if quota_match:
                used_value = float(quota_match.group(1))
                used_unit = quota_match.group(2)
                total_value = float(quota_match.group(3))
                total_unit = quota_match.group(4)
                
                # 转换为字节数
                unit_multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
                
                quota_used_bytes = int(used_value * unit_multipliers.get(used_unit, 1))
                quota_total_bytes = int(total_value * unit_multipliers.get(total_unit, 1))
                
                parsed_info['quota_used'] = quota_used_bytes
                parsed_info['quota_total'] = quota_total_bytes
                parsed_info['quota_used_readable'] = f"{used_value} {used_unit}"
                parsed_info['quota_total_readable'] = f"{total_value} {total_unit}"
                
                # 计算使用百分比
                if quota_total_bytes > 0:
                    usage_percent = (quota_used_bytes / quota_total_bytes) * 100
                    parsed_info['quota_usage_percent'] = round(usage_percent, 1)
                else:
                    parsed_info['quota_usage_percent'] = 0.0
            else:
                # 如果无法解析配额，设置默认值
                parsed_info['quota_used'] = 0
                parsed_info['quota_total'] = 0
                parsed_info['quota_used_readable'] = "0 B"
                parsed_info['quota_total_readable'] = "0 B"
                parsed_info['quota_usage_percent'] = 0.0
            
            logger.debug(f"🔍 解析用户信息结果: {parsed_info}")
            
            return parsed_info
            
        except Exception as e:
            logger.error(f"❌ 解析用户信息失败: {e}")
            return {
                'user_id': 0,
                'user_name': '未知用户',
                'quota_used': 0,
                'quota_total': 0,
                'quota_used_readable': "0 B",
                'quota_total_readable': "0 B",
                'quota_usage_percent': 0.0
            }
    
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        try:
            success, stdout, stderr = self._run_baidupcs_command(['who'], timeout=10)
            
            # BaiduPCS-Py的who命令在没有默认用户时返回码可能是1，但仍有用户信息
            # 所以我们主要检查输出内容而不是返回码
            has_user_info = (
                "user id:" in stdout.lower() or 
                "用户" in stdout or
                "user name:" in stdout.lower() or
                "bduss:" in stdout.lower()
            )
            
            logger.debug(f"🔍 认证检查 - 返回码: {success}, 有用户信息: {has_user_info}")
            logger.debug(f"🔍 输出内容: {stdout[:200]}...")
            
            if has_user_info:
                logger.info("✅ 用户已认证")
                return True
            else:
                logger.warning("⚠️ 用户未认证或无有效用户信息")
                if stderr:
                    logger.debug(f"错误输出: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 认证检查失败: {e}")
            return False
    
    def add_user_by_cookies(self, cookies: str) -> Dict[str, Any]:
        """通过cookies添加用户"""
        try:
            # 移除不存在的--no-check参数，使用正确的命令
            success, stdout, stderr = self._run_baidupcs_command([
                'useradd', 
                '--cookies', cookies
            ], timeout=30)  # 30秒超时
            
            if success:
                logger.info(f"✅ 用户添加成功")
                return {"success": True, "message": "用户添加成功"}
            else:
                error_msg = stderr or stdout or "未知错误"
                logger.error(f"❌ 添加用户失败: {error_msg}")
                
                # 检查是否是因为用户已存在
                if "already exist" in error_msg.lower() or "已存在" in error_msg:
                    logger.info("⚠️ 用户可能已存在，尝试检查当前用户")
                    if self.is_authenticated():
                        return {"success": True, "message": "用户已存在且已认证"}
                
                return {"success": False, "message": f"添加用户失败: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ 添加用户异常: {e}")
            return {"success": False, "message": f"添加用户失败: {str(e)}"}
    
    def add_user_by_bduss(self, bduss: str, stoken: str = None) -> Dict[str, Any]:
        """通过BDUSS添加用户"""
        try:
            args = ['useradd', '--bduss', bduss]
            if stoken:
                # 注意：检查BaiduPCS-Py是否支持stoken参数
                args.extend(['--stoken', stoken])
            
            success, stdout, stderr = self._run_baidupcs_command(args, timeout=30)
            
            if success:
                logger.info(f"✅ 用户添加成功")
                return {"success": True, "message": "用户添加成功"}
            else:
                error_msg = stderr or stdout or "未知错误"
                logger.error(f"❌ 添加用户失败: {error_msg}")
                
                # 检查是否是因为用户已存在
                if "already exist" in error_msg.lower() or "已存在" in error_msg:
                    logger.info("⚠️ 用户可能已存在，尝试检查当前用户")
                    if self.is_authenticated():
                        return {"success": True, "message": "用户已存在且已认证"}
                
                return {"success": False, "message": f"添加用户失败: {error_msg}"}
                
        except Exception as e:
            logger.error(f"❌ 添加用户异常: {e}")
            return {"success": False, "message": f"添加用户失败: {str(e)}"}
    
    def get_user_info(self) -> Dict[str, Any]:
        """获取用户信息"""
        try:
            success, stdout, stderr = self._run_baidupcs_command(['who'], timeout=10)
            
            if success:
                return {"success": True, "info": stdout}
            else:
                return {"success": False, "message": "获取用户信息失败"}
                
        except Exception as e:
            return {"success": False, "message": f"获取用户信息失败: {str(e)}"}
    
    def download_file(self, remote_path: str, local_path: str, 
                     downloader: str = "me", concurrency: int = 5) -> Dict[str, Any]:
        """下载文件 - 使用正确的命令行参数"""
        try:
            logger.info(f"🔄 开始下载文件: {remote_path} -> {local_path}")
            
            if not self.is_authenticated():
                return {"success": False, "message": "用户未认证"}
            
            # 确保本地目录存在
            local_dir = os.path.dirname(local_path)
            if local_dir:
                os.makedirs(local_dir, exist_ok=True)
            
            # 构建下载命令 - 使用正确的参数
            cmd_args = [
                'download',
                remote_path,
                '--outdir', local_dir,
                '--downloader', downloader,
                '-s', str(concurrency),  # 正确的并发参数
                '--chunk-size', '4M'     # 根据官方文档限制为4M
            ]
            
            logger.info(f"🔧 执行下载命令: BaiduPCS-Py {' '.join(cmd_args)}")
            
            # 执行下载命令
            success, stdout, stderr = self._run_baidupcs_command(cmd_args, timeout=7200)  # 2小时超时
            
            # 检查文件是否下载成功
            expected_file = os.path.join(local_dir, os.path.basename(remote_path))
            if os.path.exists(expected_file) and os.path.getsize(expected_file) > 0:
                # 如果目标文件路径不同，移动文件
                if expected_file != local_path:
                    shutil.move(expected_file, local_path)
                
                file_size = os.path.getsize(local_path)
                logger.info(f"✅ 文件下载成功: {local_path} ({self._format_size(file_size)})")
                
                return {
                    "success": True,
                    "message": "文件下载成功",
                    "local_path": local_path,
                    "file_size": file_size,
                    "file_size_readable": self._format_size(file_size)
                }
            else:
                error_msg = stderr or stdout or "下载失败，文件不存在或为空"
                logger.error(f"❌ 下载失败: {error_msg}")
                return {"success": False, "message": f"下载失败: {error_msg}"}
            
        except Exception as e:
            logger.error(f"❌ 下载文件异常: {e}")
            return {"success": False, "message": f"下载失败: {str(e)}"}
    
    def get_file_list(self, path: str = "/") -> Dict[str, Any]:
        """获取文件列表 - 使用正确的 BaiduPCS-Py 命令参数"""
        try:
            if not self.is_authenticated():
                return {"success": False, "message": "用户未认证"}
            
            # 根据 BaiduPCS-Py 官方文档，ls 命令的正确用法是：
            # BaiduPCS-Py ls [OPTIONS] [REMOTEPATHS]...
            # 先尝试最基本的 ls 命令，不使用可能不存在的参数
            success, stdout, stderr = self._run_baidupcs_command(['ls', path], timeout=30)
            
            # 对于 ls 命令，即使返回码非0，只要有输出内容就可能是成功的
            if not success and not stdout.strip():
                error_msg = stderr or "获取文件列表失败"
                logger.error(f"❌ 获取文件列表失败: {error_msg}")
                return {"success": False, "message": f"获取文件列表失败: {error_msg}"}
            
            if not stdout.strip():
                logger.info("📁 目录为空")
                return {"success": True, "files": []}
            
            # 解析 BaiduPCS-Py ls 命令的实际输出格式
            files = []
            lines = stdout.split('\n')
            logger.debug(f"🔍 解析文件列表输出，共 {len(lines)} 行")
            logger.debug(f"🔍 原始输出:\n{stdout}")
            
            for i, line in enumerate(lines):
                original_line = line
                line = line.strip()
                if not line:
                    continue
                
                # 跳过表头、路径显示和分隔符
                if (line.startswith('─') or 
                    line.startswith('=') or
                    line == 'Path' or
                    line.startswith('  Path') or
                    line == path or  # 跳过路径显示行
                    line.startswith('总计') or
                    line.startswith('共') or
                    'items' in line.lower()):
                    logger.debug(f"⏭️ 跳过表头行: {line}")
                    continue
                
                try:
                    # BaiduPCS-Py ls 的实际输出格式：
                    # d 目录名
                    # - 文件名
                    
                    is_dir = False
                    filename = ""
                    
                    if line.startswith('d '):
                        # 目录
                        is_dir = True
                        filename = line[2:].strip()
                    elif line.startswith('- '):
                        # 文件
                        is_dir = False
                        filename = line[2:].strip()
                    else:
                        # 其他格式，直接当作文件名处理
                        filename = line
                        is_dir = False
                    
                    # 如果文件名为空，跳过
                    if not filename:
                        logger.debug(f"⏭️ 跳过空文件名行: {original_line}")
                        continue
                    
                    # 生成 fs_id (使用文件名的哈希)
                    fs_id = f"file_{abs(hash(filename)) % 1000000}"
                    
                    # 构建文件路径
                    if path == '/':
                        file_path = f"/{filename}"
                    elif path.endswith('/'):
                        file_path = f"{path}{filename}"
                    else:
                        file_path = f"{path}/{filename}"
                    
                    # 判断是否为媒体文件
                    is_media = not is_dir and self._is_media_file(filename)
                    
                    # 生成时间戳（当前时间）
                    current_time = int(time.time())
                    
                    file_info = {
                        'fs_id': str(fs_id),
                        'filename': filename,
                        'path': file_path,
                        'is_dir': is_dir,
                        'is_media': is_media,
                        'size': 0,  # BaiduPCS-Py 基础 ls 命令不返回大小信息
                        'size_readable': "未知大小",
                        'ctime': current_time,
                        'mtime': current_time
                    }
                    
                    files.append(file_info)
                    logger.debug(f"✅ 解析文件: '{filename}' (dir: {is_dir}, media: {is_media})")
                
                except Exception as parse_error:
                    logger.warning(f"⚠️ 解析文件行失败 {i}: '{original_line}', 错误: {parse_error}")
                    continue
            
            logger.info(f"✅ 解析文件列表成功，共 {len(files)} 个项目")
            return {"success": True, "files": files}
                
        except Exception as e:
            logger.error(f"❌ 获取文件列表异常: {e}")
            return {"success": False, "message": f"获取文件列表失败: {str(e)}"}
    
    def _is_media_file(self, filename: str) -> bool:
        """判断是否为媒体文件"""
        file_ext = os.path.splitext(filename)[1].lower()
        return file_ext in self.video_extensions or file_ext in self.audio_extensions
    
    def upload_file(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        """上传文件"""
        try:
            if not self.is_authenticated():
                return {"success": False, "message": "用户未认证"}
            
            if not os.path.exists(local_path):
                return {"success": False, "message": f"本地文件不存在: {local_path}"}
            
            remote_dir = os.path.dirname(remote_path)
            
            success, stdout, stderr = self._run_baidupcs_command(['upload', local_path, remote_dir], timeout=7200)
            
            if success:
                return {"success": True, "message": "上传成功"}
            else:
                return {"success": False, "message": f"上传失败: {stderr or stdout}"}
                
        except Exception as e:
            return {"success": False, "message": f"上传失败: {str(e)}"}

# 创建全局实例
baidupcs_service = BaiduPCSService()