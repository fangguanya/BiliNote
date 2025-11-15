#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一的百度网盘API路由
基于BaiduPCS-Py命令行工具，提供完整的百度网盘操作接口
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel

from app.utils.response import ResponseWrapper as R
from app.utils.logger import get_logger
from app.downloaders.baidupcs_downloader import BaiduPCSDownloader, BaiduPanDownloader
from app.third_party.baidupcs_api import BaiduPCSDownloader as BaiduPCSApiDownloader
from app.exceptions.auth_exceptions import AuthRequiredException

logger = get_logger(__name__)
router = APIRouter(prefix="/baidupcs", tags=["百度网盘"])

# 使用 API 下载器替代命令行工具
api_downloader = BaiduPCSApiDownloader()


# =============== 请求模型 ===============

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


class RapidUploadRequest(BaseModel):
    """秒传请求"""
    links: List[str]
    target_dir: str = "/"


class CreateShareRequest(BaseModel):
    """创建分享请求"""
    fs_ids: List[str]
    password: Optional[str] = ""
    period: int = 0  # 0永久 1一天 7七天


class OfflineTaskRequest(BaseModel):
    """离线下载任务请求"""
    source_url: str
    save_path: str
    file_types: Optional[List[str]] = None


class BaiduPCSUserData(BaseModel):
    """百度网盘用户数据"""
    cookies: Optional[str] = None
    bduss: Optional[str] = None
    stoken: Optional[str] = None


# =============== 用户管理接口 ===============

@router.get("/debug/routes", summary="调试：显示所有路由")
def debug_routes():
    """调试接口：显示当前路由配置"""
    return {
        "message": "百度网盘路由正常",
        "router_prefix": "/baidupcs",
        "app_prefix": "/api",
        "available_endpoints": [
            "POST /api/baidupcs/add_user",
            "POST /api/baidupcs/remove_user",
            "GET /api/baidupcs/users",
            "GET /api/baidupcs/auth_status",
            "GET /api/baidupcs/current_user",
            "GET /api/baidupcs/file_list",
        ],
        "note": "完整路径 = /api + /baidupcs + 端点路径"
    }

@router.post("/add_user", summary="添加百度网盘用户")
async def add_baidupcs_user(user_data: BaiduPCSUserData):
    """
    添加百度网盘用户
    支持通过 Cookies 或 BDUSS 添加用户
    """
    # 🔥🔥🔥 最前面的日志，确保函数被调用
    import sys
    print("\n" + "🔥" * 40, file=sys.stderr)
    print("🔥🔥🔥 百度网盘添加用户接口被调用！！！", file=sys.stderr)
    print(f"🔥🔥🔥 接收到的数据: cookies={'有' if user_data.cookies else '无'}, bduss={'有' if user_data.bduss else '无'}", file=sys.stderr)
    print("🔥" * 40 + "\n", file=sys.stderr)
    
    try:
        logger.error("=" * 80)
        logger.error("🔥🔥🔥 [百度网盘] 开始添加用户")
        if user_data.cookies:
            logger.error(f"🔥 接收到完整Cookie字符串，长度: {len(user_data.cookies)}")
        else:
            logger.error(f"🔥 接收到单独的BDUSS/STOKEN - bduss: {'有' if user_data.bduss else '无'}, stoken: {'有' if user_data.stoken else '无'}")
        logger.error("=" * 80)
        
        # 首先检查是否已经有认证用户
        if api_downloader.is_authenticated():
            user_info = api_downloader.get_user_info()
            if user_info.get("success", False):
                logger.info("✅ 用户已经认证，无需重复添加")
                return {
                    "success": True,
                    "message": "用户已认证",
                    "user_info": user_info.get("info", "")
                }
        
        # 根据提供的数据类型添加用户
        if user_data.cookies:
            logger.info("🔧 使用 Cookies 添加用户")
            result = api_downloader.add_user_by_cookies(user_data.cookies)
        elif user_data.bduss:
            logger.info("🔧 使用 BDUSS 添加用户")
            result = api_downloader.add_user_by_bduss(user_data.bduss, user_data.stoken)
        else:
            return {
                "success": False,
                "message": "请提供 cookies 或 bduss"
            }
        
        # 如果添加失败，增强错误提示
        if not result.get("success", False):
            error_msg = result.get("message", "未知错误")
            
            # 检查是否是BDUSS过期的错误（31045）
            if "31045" in str(error_msg) or "用户不存在" in str(error_msg) or "用户未登录" in str(error_msg):
                logger.error("❌ BDUSS已过期或无效")
                return {
                    "success": False,
                    "message": "BDUSS已过期或无效，请重新获取最新的BDUSS",
                    "error_code": "31045",
                    "help": "如何获取有效BDUSS：\n1. 打开浏览器无痕模式\n2. 访问 https://pan.baidu.com\n3. 登录账号\n4. F12 → Application → Cookies → 复制BDUSS的值"
                }
        
        # 如果添加成功，获取用户信息
        if result.get("success", False):
            user_info = api_downloader.get_user_info()
            if user_info.get("success", False):
                result["user_info"] = user_info.get("info", "")
        
        logger.info(f"✅ 用户添加结果: {result.get('message', '未知')}")
        return result
        
    except Exception as e:
        logger.error(f"❌ 添加用户失败: {e}")
        return {
            "success": False,
            "message": f"添加用户失败: {str(e)}"
        }


@router.post("/remove_user")
def remove_user(request: RemoveUserRequest):
    """移除百度网盘用户"""
    try:
        logger.info(f"🗑️ 移除用户: {request.user_id}")
        
        # TODO: 实现用户移除功能
        # downloader = BaiduPCSDownloader()
        # success = downloader.remove_user(request.user_id)
        
        return R.success({"message": "用户移除功能待实现"})
            
    except Exception as e:
        logger.error(f"❌ 移除用户失败: {e}")
        return R.error(f"移除用户失败: {str(e)}", code=500)


@router.get("/users")
def list_users():
    """获取用户列表"""
    try:
        # TODO: 实现用户列表功能
        return R.success({
            "users": [],
            "count": 0,
            "message": "用户列表功能待实现"
        })
        
    except Exception as e:
        logger.error(f"❌ 获取用户列表失败: {e}")
        return R.error(f"获取用户列表失败: {str(e)}", code=500)


@router.get("/current_user")
def get_current_user():
    """获取当前用户信息"""
    try:
        logger.info("🔍 API调用：获取当前用户信息")
        
        # 添加详细的调试信息
        is_auth = api_downloader.is_authenticated()
        logger.info(f"📋 API认证检查结果: {is_auth}")
        
        if is_auth:
            user_info = api_downloader.get_user_info()
            logger.info(f"📋 API用户信息获取: {user_info.get('success', False)}")
            
            return R.success({
                "authenticated": True,
                "user_info": user_info
            })
        else:
            logger.warning("⚠️ API认证检查失败")
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
        is_authenticated = api_downloader.is_authenticated()
        
        if is_authenticated:
            user_info_raw = api_downloader.get_user_info()
            
            if user_info_raw.get("success", False):
                # API 返回的用户信息已经是解析好的
                return R.success({
                    "authenticated": True,
                    "message": "已认证",
                    "user_info": {
                        "user_id": user_info_raw.get("user_id"),
                        "user_name": user_info_raw.get("user_name"),
                        "quota": user_info_raw.get("quota"),
                        "used": user_info_raw.get("used")
                    }
                })
            else:
                return R.success({
                    "authenticated": False,
                    "message": "获取用户信息失败"
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


# =============== 文件管理接口 ===============

@router.get("/file_list")
def get_file_list(
    path: str = Query("/", description="目录路径"),
    order: str = Query("time", description="排序方式: time/name/size"),
    desc: bool = Query(True, description="是否降序"),
    media_only: bool = Query(False, description="是否只显示媒体文件"),
    recursive: bool = Query(False, description="是否递归列出子目录"),
    use_cache: bool = Query(True, description="是否使用缓存")
):
    """
    获取文件列表
    
    🚀 优化：
    - 添加了缓存机制，默认缓存5分钟（非递归）或10分钟（递归）
    - 支持通过 use_cache=False 强制刷新
    """
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        # 🚀 直接使用API下载器，避免中间层
        result = api_downloader.list_files(path, recursive=recursive, use_cache=use_cache)
        
        if not result.get("success", False):
            return R.error(result.get("message", "获取文件列表失败"), code=500)
        
        files = result.get("files", [])
        
        # 如果只要媒体文件，进行过滤
        if media_only:
            files = [f for f in files if f.get("is_media", False)]
        
        # 统计媒体文件数量
        media_count = len([f for f in files if f.get("is_media", False)])
        
        return R.success({
            "files": files,
            "total": len(files),
            "media_count": media_count,
            "current_path": path,
            "from_cache": use_cache and result.get("fetch_time", 0) < 0.1,  # 如果耗时很短，很可能来自缓存
            "fetch_time": result.get("fetch_time", 0)
        })
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 获取文件列表失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return R.error(f"获取文件列表失败: {str(e)}", code=500)


@router.get("/search")
def search_files(
    keyword: str = Query(..., description="搜索关键词"),
    path: str = Query("/", description="搜索路径"),
    media_only: bool = Query(False, description="是否只搜索媒体文件")
):
    """搜索文件"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        # TODO: 实现搜索功能
        return R.success({
            "files": [],
            "total": 0,
            "keyword": keyword,
            "search_path": path,
            "message": "搜索功能待实现"
        })
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 搜索文件失败: {e}")
        return R.error(f"搜索文件失败: {str(e)}", code=500)


@router.get("/media_files")
def get_media_files(path: str = Query("/", description="目录路径")):
    """获取媒体文件"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        downloader = BaiduPCSDownloader()
        files = downloader.get_file_list(path)
        media_files = [f for f in files if f.get("is_media", False)]
        
        return R.success({
            "files": media_files,
            "total": len(media_files),
            "media_path": path
        })
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 获取媒体文件失败: {e}")
        return R.error(f"获取媒体文件失败: {str(e)}", code=500)


# =============== 下载上传接口 ===============

@router.post("/download")
def download_file(request: DownloadRequest):
    """下载文件"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        downloader = BaiduPCSDownloader()
        
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


@router.post("/enhanced_download")
def download_with_enhanced_features(
    url: str = Body(..., embed=True, description="百度网盘链接（支持baidu_pan://协议）"),
    output_dir: Optional[str] = Body(None, embed=True, description="输出目录"),
    need_video: bool = Body(False, embed=True, description="是否需要视频文件")
):
    """增强的下载功能（支持baidu_pan://协议）"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        downloader = BaiduPanDownloader()
        result = downloader.download(url, output_dir, need_video=need_video)
        
        if result.success:
            return R.success({
                "result": {
                    "file_path": result.file_path,
                    "title": result.title,
                    "duration": result.duration,
                    "platform": result.platform,
                    "video_id": result.video_id,
                    "raw_info": result.raw_info,
                    "video_path": result.video_path
                },
                "message": "下载成功"
            })
        else:
            return R.error(f"下载失败: {result.error}", code=500)
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 下载失败: {e}")
        return R.error(f"下载失败: {str(e)}", code=500)


@router.post("/upload")
def upload_file(request: UploadRequest):
    """上传文件"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        downloader = BaiduPCSDownloader()
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


# =============== 视频信息接口 ===============

@router.get("/video_info")
def get_video_info(url: str = Query(..., description="视频URL或路径")):
    """获取视频信息"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        downloader = BaiduPCSDownloader()
        info = downloader.get_video_info(url)
        
        if "error" in info:
            return R.error(info["error"], code=400)
        
        return R.success(info)
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 获取视频信息失败: {e}")
        return R.error(f"获取视频信息失败: {str(e)}", code=500)


# =============== 任务管理接口 ===============

@router.post("/create_tasks")
def create_tasks(request: CreateTaskRequest):
    """创建下载任务"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        # TODO: 实现任务创建功能
        return R.success({
            "message": "任务创建功能待实现",
            "tasks": [],
            "count": 0
        })
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 创建任务失败: {e}")
        return R.error(f"创建任务失败: {str(e)}", code=500)


# =============== 批量操作接口 ===============

@router.post("/batch_download")
def batch_download_with_enhanced_features(
    urls: List[str] = Body(..., embed=True, description="百度网盘链接列表"),
    output_dir: Optional[str] = Body(None, embed=True, description="输出目录"),
    max_files: int = Body(10, embed=True, description="最大文件数量")
):
    """批量下载"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        downloader = BaiduPanDownloader()
        results = []
        
        for url in urls[:max_files]:
            try:
                result = downloader.download(url, output_dir)
                if result.success:
                    results.append({
                        "file_path": result.file_path,
                        "title": result.title,
                        "duration": result.duration,
                        "platform": result.platform,
                        "video_id": result.video_id,
                        "raw_info": result.raw_info,
                        "success": True
                    })
                else:
                    results.append({
                        "url": url,
                        "error": result.error,
                        "success": False
                    })
            except Exception as e:
                results.append({
                    "url": url,
                    "error": str(e),
                    "success": False
                })
        
        successful = len([r for r in results if r.get("success", False)])
        
        return R.success({
            "results": results,
            "successful": successful,
            "total": len(urls),
            "message": f"批量下载完成，成功处理 {successful}/{len(urls)} 个文件"
        })
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 批量下载失败: {e}")
        return R.error(f"批量下载失败: {str(e)}", code=500)


# =============== 使用指南接口 ===============

@router.get("/usage_guide")
def get_usage_guide():
    """获取使用指南"""
    return R.success({
        "title": "统一百度网盘API使用指南",
        "description": "基于BaiduPCS-Py命令行工具的完整百度网盘操作接口",
        "setup_steps": [
            {
                "step": 1,
                "title": "获取Cookie",
                "description": "在浏览器中登录百度网盘，获取完整的cookie字符串",
                "details": [
                    "访问 https://pan.baidu.com 并登录",
                    "按F12打开开发者工具",
                    "转到Application -> Cookies -> https://pan.baidu.com",
                    "复制所有cookie，特别是BDUSS、STOKEN、PSTM"
                ]
            },
            {
                "step": 2,
                "title": "添加用户",
                "description": "调用 /baidupcs/add_user 接口，传入cookies",
                "example": {
                    "method": "POST",
                    "url": "/baidupcs/add_user",
                    "body": {
                        "cookies": "BDUSS=xxx; STOKEN=xxx; PSTM=xxx; BAIDUID=xxx; ...",
                        "bduss": "可选，如果cookies中已包含BDUSS则不需要"
                    }
                }
            },
            {
                "step": 3,
                "title": "使用功能",
                "description": "添加用户后即可使用各种文件操作功能"
            }
        ],
        "api_categories": {
            "用户管理": [
                "POST /baidupcs/add_user - 添加用户",
                "GET /baidupcs/auth_status - 检查认证状态",
                "GET /baidupcs/current_user - 获取当前用户信息"
            ],
            "文件管理": [
                "GET /baidupcs/file_list - 获取文件列表",
                "GET /baidupcs/media_files - 获取媒体文件",
                "GET /baidupcs/search - 搜索文件"
            ],
            "下载上传": [
                "POST /baidupcs/download - 基础下载",
                "POST /baidupcs/enhanced_download - 增强下载(支持baidu_pan://)",
                "POST /baidupcs/batch_download - 批量下载",
                "POST /baidupcs/upload - 上传文件"
            ],
            "信息查询": [
                "GET /baidupcs/video_info - 获取视频信息",
                "GET /baidupcs/usage_guide - 获取使用指南"
            ]
        },
        "advantages": [
            "基于BaiduPCS-Py命令行工具，稳定可靠",
            "支持baidu_pan://协议链接",
            "完整的用户认证管理",
            "支持批量文件操作",
            "提供详细的错误信息和使用指南"
        ],
        "required_data": {
            "cookies": {
                "description": "完整的百度网盘cookie字符串",
                "format": "BDUSS=xxx; STOKEN=xxx; PSTM=xxx; BAIDUID=xxx; ...",
                "required_fields": ["BDUSS"],
                "optional_fields": ["STOKEN", "PSTM", "BAIDUID", "PASSID"]
            }
        }
    })

# =============== 任务队列管理接口 ===============

@router.get("/queue/status")
def get_queue_status():
    """获取下载队列状态"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        queue_info = api_downloader.get_queue_info()
        return R.success(queue_info)
        
    except Exception as e:
        logger.error(f"❌ 获取队列状态失败: {e}")
        return R.error(f"获取队列状态失败: {str(e)}", code=500)


@router.get("/task/{task_id}/status")
def get_task_status(task_id: str):
    """获取特定任务状态"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        status = api_downloader.get_task_status(task_id)
        if not status:
            return R.error("任务不存在", code=404)
        
        return R.success(status)
        
    except Exception as e:
        logger.error(f"❌ 获取任务状态失败: {e}")
        return R.error(f"获取任务状态失败: {str(e)}", code=500)


@router.post("/task/{task_id}/cancel")
def cancel_task(task_id: str):
    """取消下载任务"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        success = api_downloader.cancel_task(task_id)
        if success:
            return R.success({"message": "任务已取消", "task_id": task_id})
        else:
            return R.error("无法取消任务", code=400)
        
    except Exception as e:
        logger.error(f"❌ 取消任务失败: {e}")
        return R.error(f"取消任务失败: {str(e)}", code=500)


@router.post("/download_async")
def download_file_async(request: DownloadRequest):
    """异步下载文件"""
    try:
        if not api_downloader.is_authenticated():
            return R.error("未认证，请先添加用户", code=401)
        
        # 使用异步下载模式
        result = api_downloader.download_file(
            remote_path=request.remote_path,
            local_path=request.local_path,
            wait_for_completion=False
        )
        
        return R.success(result)
        
    except AuthRequiredException as e:
        return R.error("认证已过期，请重新添加用户", code=401)
    except Exception as e:
        logger.error(f"❌ 异步下载失败: {e}")
        return R.error(f"异步下载失败: {str(e)}", code=500)


# =============== 全局下载管理接口 ===============

@router.get("/global/download/status")
def get_global_download_status():
    """获取全局下载状态"""
    try:
        from app.services.global_download_manager import global_download_manager
        
        status = global_download_manager.get_global_status()
        return R.success(status)
        
    except Exception as e:
        logger.error(f"❌ 获取全局下载状态失败: {e}")
        return R.error(f"获取全局下载状态失败: {str(e)}", code=500)


@router.get("/global/task/{task_id}/status")
def get_global_task_status(task_id: str):
    """获取全局任务状态"""
    try:
        from app.services.global_download_manager import global_download_manager
        
        status = global_download_manager.get_task_status(task_id)
        if not status:
            return R.error("任务不存在", code=404)
        
        return R.success(status)
        
    except Exception as e:
        logger.error(f"❌ 获取全局任务状态失败: {e}")
        return R.error(f"获取全局任务状态失败: {str(e)}", code=500)


@router.post("/global/task/{task_id}/cancel")
def cancel_global_task(task_id: str):
    """取消全局下载任务"""
    try:
        from app.services.global_download_manager import global_download_manager
        
        success = global_download_manager.cancel_task(task_id)
        if success:
            return R.success({"message": "任务已取消", "task_id": task_id})
        else:
            return R.error("无法取消任务", code=400)
        
    except Exception as e:
        logger.error(f"❌ 取消全局任务失败: {e}")
        return R.error(f"取消全局任务失败: {str(e)}", code=500)


# =============== 缓存管理接口 ===============

@router.post("/cache/clear")
def clear_cache():
    """清空百度网盘文件列表缓存"""
    try:
        from app.utils.cache_manager import clear_baidu_pan_cache
        
        clear_baidu_pan_cache()
        return R.success({"message": "缓存已清空"})
        
    except Exception as e:
        logger.error(f"❌ 清空缓存失败: {e}")
        return R.error(f"清空缓存失败: {str(e)}", code=500)


@router.get("/cache/stats")
def get_cache_stats():
    """获取缓存统计信息"""
    try:
        from app.utils.cache_manager import cache_manager
        
        stats = cache_manager.get_all_stats()
        return R.success(stats)
        
    except Exception as e:
        logger.error(f"❌ 获取缓存统计失败: {e}")
        return R.error(f"获取缓存统计失败: {str(e)}", code=500) 