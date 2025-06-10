#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BaiduPCS-Py API路由
提供基于BaiduPCS-Py的百度网盘用户管理和文件操作接口
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.utils.response import ResponseWrapper as R
from app.utils.logger import get_logger
from app.downloaders.baidupcs_downloader import BaiduPCSDownloader
from app.exceptions.auth_exceptions import AuthRequiredException

logger = get_logger(__name__)
router = APIRouter(prefix="/baidupcs", tags=["BaiduPCS"])


class AddUserRequest(BaseModel):
    """添加用户请求"""
    cookies: str
    bduss: Optional[str] = None


class RemoveUserRequest(BaseModel):
    """移除用户请求"""
    user_id: Optional[int] = None


class FileListRequest(BaseModel):
    """文件列表请求"""
    path: str = "/"
    order: str = "time"
    desc: bool = True
    recursion: bool = False


class SearchRequest(BaseModel):
    """搜索请求"""
    keyword: str
    path: str = "/"


class DownloadRequest(BaseModel):
    """下载请求"""
    remote_path: str
    local_path: str
    quality: str = "origin"


class UploadRequest(BaseModel):
    """上传请求"""
    local_path: str
    remote_path: str


class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    files: List[Dict[str, Any]]
    task_config: Dict[str, Any]


@router.post("/add_user")
def add_user(request: AddUserRequest):
    """
    添加百度网盘用户
    相当于 BaiduPCS-Py useradd --cookies "cookies值" --bduss "bduss值"
    """
    try:
        logger.info("📝 开始添加百度网盘用户")
        
        downloader = BaiduPCSDownloader()
        success = downloader.add_user(request.cookies, request.bduss)
        
        if success:
            # 获取用户信息
            user_info = downloader.get_current_user_info()
            return R.success({
                "message": "用户添加成功",
                "user_info": user_info
            })
        else:
            return R.error("用户添加失败", code=400)
            
    except Exception as e:
        logger.error(f"❌ 添加用户失败: {e}")
        return R.error(f"添加用户失败: {str(e)}", code=500)


@router.post("/remove_user")
def remove_user(request: RemoveUserRequest):
    """移除百度网盘用户"""
    try:
        logger.info(f"🗑️ 移除用户: {request.user_id}")
        
        downloader = BaiduPCSDownloader()
        success = downloader.remove_user(request.user_id)
        
        if success:
            return R.success({"message": "用户移除成功"})
        else:
            return R.error("用户移除失败", code=400)
            
    except Exception as e:
        logger.error(f"❌ 移除用户失败: {e}")
        return R.error(f"移除用户失败: {str(e)}", code=500)


@router.get("/users")
def list_users():
    """获取用户列表"""
    try:
        downloader = BaiduPCSDownloader()
        users = downloader.get_users()
        
        return R.success({
            "users": users,
            "count": len(users)
        })
        
    except Exception as e:
        logger.error(f"❌ 获取用户列表失败: {e}")
        return R.error(f"获取用户列表失败: {str(e)}", code=500)


@router.get("/current_user")
def get_current_user():
    """获取当前用户信息"""
    try:
        downloader = BaiduPCSDownloader()
        user_info = downloader.get_current_user_info()
        
        if user_info:
            return R.success({
                "authenticated": True,
                "user_info": user_info
            })
        else:
            return R.success({
                "authenticated": False,
                "message": "未找到已认证的用户"
            })
            
    except Exception as e:
        logger.error(f"❌ 获取当前用户失败: {e}")
        return R.error(f"获取当前用户失败: {str(e)}", code=500)


@router.get("/auth_status")
def get_auth_status():
    """检查认证状态"""
    try:
        downloader = BaiduPCSDownloader()
        is_authenticated = downloader.is_authenticated()
        
        if is_authenticated:
            user_info = downloader.get_current_user_info()
            return R.success({
                "authenticated": True,
                "message": "已认证",
                "user_info": user_info
            })
        else:
            return R.success({
                "authenticated": False,
                "message": "未认证，请添加用户",
                "setup_guide": {
                    "steps": [
                        "1. 在浏览器中访问 https://pan.baidu.com",
                        "2. 登录您的百度账号",
                        "3. 按F12打开开发者工具",
                        "4. 转到 Application/应用 -> Storage/存储 -> Cookies",
                        "5. 选择 https://pan.baidu.com",
                        "6. 复制所有cookie值（特别是BDUSS）",
                        "7. 调用 /baidupcs/add_user 接口添加用户"
                    ],
                    "required_cookies": ["BDUSS", "STOKEN", "PSTM"],
                    "tips": [
                        "确保复制完整的cookie字符串",
                        "cookie中必须包含BDUSS字段",
                        "如果添加失败，请尝试刷新页面后重新复制cookie"
                    ]
                }
            })
            
    except Exception as e:
        logger.error(f"❌ 检查认证状态失败: {e}")
        return R.error(f"检查认证状态失败: {str(e)}", code=500)


@router.get("/file_list")
def get_file_list(path: str = "/", order: str = "time", desc: bool = True):
    """获取文件列表"""
    try:
        downloader = BaiduPCSDownloader()
        
        if not downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        files = downloader.get_file_list(path)
        media_files = [f for f in files if f.get("is_media", False)]
        
        return R.success({
            "files": files,
            "total": len(files),
            "media_count": len(media_files),
            "current_path": path
        })
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 获取文件列表失败: {e}")
        return R.error(f"获取文件列表失败: {str(e)}", code=500)


@router.get("/search")
def search_files(keyword: str, path: str = "/"):
    """搜索文件"""
    try:
        downloader = BaiduPCSDownloader()
        
        if not downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        files = downloader.search_files(keyword, path)
        
        return R.success({
            "files": files,
            "total": len(files),
            "keyword": keyword,
            "search_path": path
        })
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 搜索文件失败: {e}")
        return R.error(f"搜索文件失败: {str(e)}", code=500)


@router.get("/media_files")
def get_media_files(path: str = "/"):
    """获取媒体文件"""
    try:
        downloader = BaiduPCSDownloader()
        
        if not downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        files = downloader.get_media_files(path)
        
        return R.success({
            "files": files,
            "total": len(files),
            "media_path": path
        })
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 获取媒体文件失败: {e}")
        return R.error(f"获取媒体文件失败: {str(e)}", code=500)


@router.post("/download")
def download_file(request: DownloadRequest):
    """下载文件"""
    try:
        downloader = BaiduPCSDownloader()
        
        if not downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        # 根据文件扩展名选择下载方法
        from pathlib import Path
        ext = Path(request.remote_path).suffix.lower()
        
        if ext in downloader.audio_extensions:
            result = downloader.download_audio(
                request.remote_path, 
                request.local_path,
                title=Path(request.remote_path).stem
            )
        elif ext in downloader.video_extensions:
            result = downloader.download_video(
                request.remote_path,
                request.local_path,
                title=Path(request.remote_path).stem
            )
        else:
            return R.error("不支持的文件类型", code=400)
        
        if result.success:
            return R.success({
                "message": "下载成功",
                "file_path": result.file_path,
                "title": result.title,
                "file_size": result.file_size,
                "format": result.format
            })
        else:
            return R.error(f"下载失败: {result.error}", code=500)
            
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 下载文件失败: {e}")
        return R.error(f"下载文件失败: {str(e)}", code=500)


@router.post("/upload")
def upload_file(request: UploadRequest):
    """上传文件"""
    try:
        downloader = BaiduPCSDownloader()
        
        if not downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        success = downloader.upload_file(request.local_path, request.remote_path)
        
        if success:
            return R.success({"message": "上传成功"})
        else:
            return R.error("上传失败", code=500)
            
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 上传文件失败: {e}")
        return R.error(f"上传文件失败: {str(e)}", code=500)


@router.post("/create_tasks")
def create_tasks(request: CreateTaskRequest):
    """创建下载任务"""
    try:
        downloader = BaiduPCSDownloader()
        
        if not downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        tasks = downloader.create_download_task(request.files, request.task_config)
        
        return R.success({
            "message": "任务创建成功",
            "tasks": tasks,
            "count": len(tasks)
        })
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 创建任务失败: {e}")
        return R.error(f"创建任务失败: {str(e)}", code=500)


@router.get("/video_info")
def get_video_info(url: str):
    """获取视频信息"""
    try:
        downloader = BaiduPCSDownloader()
        
        if not downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        info = downloader.get_video_info(url)
        
        if "error" in info:
            return R.error(info["error"], code=400)
        
        return R.success(info)
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 获取视频信息失败: {e}")
        return R.error(f"获取视频信息失败: {str(e)}", code=500)


@router.get("/usage_guide")
def get_usage_guide():
    """获取使用指南"""
    return R.success({
        "title": "BaiduPCS-Py 使用指南",
        "description": "基于官方BaiduPCS-Py库的百度网盘操作接口",
        "setup_steps": [
            {
                "step": 1,
                "title": "获取Cookie",
                "description": "在浏览器中登录百度网盘，获取完整的cookie字符串"
            },
            {
                "step": 2,
                "title": "添加用户",
                "description": "调用 /baidupcs/add_user 接口，传入cookies和bduss",
                "example": {
                    "method": "POST",
                    "url": "/baidupcs/add_user",
                    "body": {
                        "cookies": "BDUSS=xxx; STOKEN=xxx; PSTM=xxx; ...",
                        "bduss": "可选，如果cookies中包含BDUSS则不需要单独传入"
                    }
                }
            },
            {
                "step": 3,
                "title": "使用功能",
                "description": "添加用户后即可使用各种文件操作功能",
                "features": [
                    "获取文件列表：/baidupcs/file_list",
                    "搜索文件：/baidupcs/search",
                    "下载文件：/baidupcs/download",
                    "上传文件：/baidupcs/upload",
                    "创建任务：/baidupcs/create_tasks"
                ]
            }
        ],
        "advantages": [
            "基于官方BaiduPCS-Py库，功能完整",
            "支持多用户管理",
            "无需手动维护cookie有效性",
            "支持批量文件操作",
            "提供完整的下载和上传功能"
        ],
        "required_data": {
            "cookies": {
                "description": "完整的百度网盘cookie字符串",
                "format": "BDUSS=xxx; STOKEN=xxx; PSTM=xxx; BAIDUID=xxx; ...",
                "required_fields": ["BDUSS"],
                "optional_fields": ["STOKEN", "PSTM", "BAIDUID", "PASSID"]
            },
            "bduss": {
                "description": "百度用户身份凭证",
                "note": "如果cookies中已包含BDUSS，则此参数可选"
            }
        }
    }) 