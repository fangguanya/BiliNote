from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.services.baidu_pcs_service import BaiduPCSService, RapidUploadInfo, ShareInfo, DownloadTask
from app.downloaders.baidu_pan_downloader import BaiduPanDownloader
from app.utils.response import ResponseWrapper as R
from app.utils.logger import get_logger
from app.exceptions.auth_exceptions import AuthRequiredException

router = APIRouter(prefix="/baidu_pan", tags=["百度网盘"])
logger = get_logger(__name__)


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


@router.get("/user_info")
def get_user_info():
    """获取用户信息"""
    try:
        pcs_service = BaiduPCSService()
        user_info = pcs_service.get_user_info()
        
        return R.success({
            "user_info": user_info,
            "message": "获取用户信息成功"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 获取用户信息失败: {e}")
        return R.error(f"获取用户信息失败: {str(e)}", code=500)


@router.get("/quota")
def get_quota_info():
    """获取网盘配额信息"""
    try:
        pcs_service = BaiduPCSService()
        quota_info = pcs_service.get_quota_info()
        
        return R.success({
            "quota": quota_info,
            "message": "获取配额信息成功"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 获取配额信息失败: {e}")
        return R.error(f"获取配额信息失败: {str(e)}", code=500)


@router.get("/files")
def list_files(
    path: str = Query("/", description="目录路径"),
    order: str = Query("time", description="排序方式: time/name/size"),
    desc: int = Query(1, description="是否降序: 1降序 0升序"),
    start: int = Query(0, description="起始位置"),
    limit: int = Query(100, description="限制数量"),
    recursion: int = Query(0, description="是否递归: 1递归 0不递归"),
    media_only: bool = Query(False, description="是否只显示媒体文件")
):
    """获取文件列表"""
    try:
        pcs_service = BaiduPCSService()
        files = pcs_service.list_files(path, order, desc, start, limit, recursion)
        
        # 如果只要媒体文件，进行过滤
        if media_only:
            files = pcs_service.filter_media_files(files)
        
        # 转换为字典格式
        files_data = []
        for file_info in files:
            file_dict = {
                "fs_id": file_info.fs_id,
                "filename": file_info.filename,
                "path": file_info.path,
                "size": file_info.size,
                "md5": file_info.md5,
                "is_dir": file_info.is_dir,
                "server_ctime": file_info.server_ctime,
                "server_mtime": file_info.server_mtime,
                "category": file_info.category,
                "category_name": pcs_service.category_map.get(file_info.category, "其他")
            }
            files_data.append(file_dict)
        
        return R.success({
            "files": files_data,
            "total": len(files_data),
            "path": path,
            "message": f"获取到 {len(files_data)} 个文件"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 获取文件列表失败: {e}")
        return R.error(f"获取文件列表失败: {str(e)}", code=500)


@router.get("/search")
def search_files(
    keyword: str = Query(..., description="搜索关键词"),
    path: str = Query("/", description="搜索路径"),
    recursion: int = Query(1, description="是否递归搜索"),
    page: int = Query(1, description="页码"),
    num: int = Query(100, description="每页数量"),
    media_only: bool = Query(False, description="是否只搜索媒体文件")
):
    """搜索文件"""
    try:
        pcs_service = BaiduPCSService()
        files = pcs_service.search_files(keyword, path, recursion, page, num)
        
        # 如果只要媒体文件，进行过滤
        if media_only:
            files = pcs_service.filter_media_files(files)
        
        # 转换为字典格式
        files_data = []
        for file_info in files:
            file_dict = {
                "fs_id": file_info.fs_id,
                "filename": file_info.filename,
                "path": file_info.path,
                "size": file_info.size,
                "md5": file_info.md5,
                "is_dir": file_info.is_dir,
                "server_ctime": file_info.server_ctime,
                "server_mtime": file_info.server_mtime,
                "category": file_info.category,
                "category_name": pcs_service.category_map.get(file_info.category, "其他")
            }
            files_data.append(file_dict)
        
        return R.success({
            "files": files_data,
            "total": len(files_data),
            "keyword": keyword,
            "message": f"搜索到 {len(files_data)} 个文件"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 搜索文件失败: {e}")
        return R.error(f"搜索文件失败: {str(e)}", code=500)


@router.get("/download_links")
def get_download_links(
    fs_ids: List[str] = Query(..., description="文件fs_id列表"),
    quality: str = Query("origin", description="下载质量: origin/high/medium/low")
):
    """获取下载链接"""
    try:
        pcs_service = BaiduPCSService()
        download_info = pcs_service.get_download_links(fs_ids, quality)
        
        return R.success({
            "download_info": download_info,
            "total": len(download_info),
            "message": f"获取到 {len(download_info)} 个下载链接"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 获取下载链接失败: {e}")
        return R.error(f"获取下载链接失败: {str(e)}", code=500)


@router.post("/rapid_upload")
def rapid_upload(request: RapidUploadRequest):
    """秒传文件"""
    try:
        pcs_service = BaiduPCSService()
        results = pcs_service.batch_rapid_upload(request.links, request.target_dir)
        
        successful = sum(1 for success in results.values() if success)
        
        return R.success({
            "results": results,
            "successful": successful,
            "total": len(request.links),
            "message": f"批量秒传完成: 成功 {successful}/{len(request.links)} 个"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 批量秒传失败: {e}")
        return R.error(f"批量秒传失败: {str(e)}", code=500)


@router.post("/parse_rapid_link")
def parse_rapid_upload_link(link: str = Body(..., embed=True)):
    """解析秒传链接"""
    try:
        pcs_service = BaiduPCSService()
        rapid_info = pcs_service.parse_rapid_upload_link(link)
        
        if rapid_info:
            return R.success({
                "rapid_info": {
                    "content_md5": rapid_info.content_md5,
                    "slice_md5": rapid_info.slice_md5,
                    "content_length": rapid_info.content_length,
                    "filename": rapid_info.filename,
                    "content_crc32": rapid_info.content_crc32,
                    "cs3l_link": rapid_info.to_cs3l_link(),
                    "simple_link": rapid_info.to_simple_link()
                },
                "message": "解析秒传链接成功"
            })
        else:
            return R.error("无法解析秒传链接", code=400)
        
    except Exception as e:
        logger.error(f"❌ 解析秒传链接失败: {e}")
        return R.error(f"解析秒传链接失败: {str(e)}", code=500)


@router.post("/share/create")
def create_share(request: CreateShareRequest):
    """创建分享链接"""
    try:
        pcs_service = BaiduPCSService()
        share_info = pcs_service.create_share(request.fs_ids, request.password, request.period)
        
        return R.success({
            "share_info": {
                "share_id": share_info.share_id,
                "uk": share_info.uk,
                "share_code": share_info.share_code,
                "extract_code": share_info.extract_code,
                "share_url": share_info.share_url,
                "expiry_time": share_info.expiry_time
            },
            "message": "创建分享链接成功"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 创建分享链接失败: {e}")
        return R.error(f"创建分享链接失败: {str(e)}", code=500)


@router.get("/share/list")
def list_shares(
    page: int = Query(1, description="页码"),
    num: int = Query(100, description="每页数量")
):
    """获取分享列表"""
    try:
        pcs_service = BaiduPCSService()
        shares = pcs_service.list_shares(page, num)
        
        # 转换为字典格式
        shares_data = []
        for share_info in shares:
            share_dict = {
                "share_id": share_info.share_id,
                "uk": share_info.uk,
                "share_code": share_info.share_code,
                "share_url": share_info.share_url,
                "title": share_info.title,
                "expiry_time": share_info.expiry_time
            }
            shares_data.append(share_dict)
        
        return R.success({
            "shares": shares_data,
            "total": len(shares_data),
            "message": f"获取到 {len(shares_data)} 个分享"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 获取分享列表失败: {e}")
        return R.error(f"获取分享列表失败: {str(e)}", code=500)


@router.delete("/share/cancel")
def cancel_share(share_ids: List[str] = Body(..., embed=True)):
    """取消分享"""
    try:
        pcs_service = BaiduPCSService()
        success = pcs_service.cancel_share(share_ids)
        
        if success:
            return R.success({
                "message": f"成功取消 {len(share_ids)} 个分享"
            })
        else:
            return R.error("取消分享失败", code=500)
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 取消分享失败: {e}")
        return R.error(f"取消分享失败: {str(e)}", code=500)


@router.post("/offline/add")
def add_offline_task(request: OfflineTaskRequest):
    """添加离线下载任务"""
    try:
        pcs_service = BaiduPCSService()
        task_id = pcs_service.add_offline_task(
            request.source_url,
            request.save_path,
            request.file_types
        )
        
        return R.success({
            "task_id": task_id,
            "message": "离线下载任务创建成功"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 添加离线任务失败: {e}")
        return R.error(f"添加离线任务失败: {str(e)}", code=500)


@router.get("/offline/list")
def list_offline_tasks(
    start: int = Query(0, description="起始位置"),
    limit: int = Query(100, description="限制数量")
):
    """获取离线下载任务列表"""
    try:
        pcs_service = BaiduPCSService()
        tasks = pcs_service.list_offline_tasks(start, limit)
        
        # 转换为字典格式
        tasks_data = []
        status_map = {0: "下载中", 1: "下载成功", 2: "下载失败", 3: "下载暂停", 4: "等待中"}
        
        for task in tasks:
            task_dict = {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "status": task.status,
                "status_name": status_map.get(task.status, "未知"),
                "file_size": task.file_size,
                "finished_size": task.finished_size,
                "progress": (task.finished_size / task.file_size * 100) if task.file_size > 0 else 0,
                "create_time": task.create_time,
                "finish_time": task.finish_time,
                "source_url": task.source_url,
                "save_path": task.save_path
            }
            tasks_data.append(task_dict)
        
        return R.success({
            "tasks": tasks_data,
            "total": len(tasks_data),
            "message": f"获取到 {len(tasks_data)} 个离线任务"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 获取离线任务失败: {e}")
        return R.error(f"获取离线任务失败: {str(e)}", code=500)


@router.delete("/offline/cancel")
def cancel_offline_task(task_ids: List[str] = Body(..., embed=True)):
    """取消离线下载任务"""
    try:
        pcs_service = BaiduPCSService()
        success = pcs_service.cancel_offline_task(task_ids)
        
        if success:
            return R.success({
                "message": f"成功取消 {len(task_ids)} 个离线任务"
            })
        else:
            return R.error("取消离线任务失败", code=500)
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 取消离线任务失败: {e}")
        return R.error(f"取消离线任务失败: {str(e)}", code=500)


@router.delete("/offline/clear")
def clear_offline_tasks():
    """清除已完成和失败的离线任务"""
    try:
        pcs_service = BaiduPCSService()
        success = pcs_service.clear_offline_tasks()
        
        if success:
            return R.success({
                "message": "清除离线任务成功"
            })
        else:
            return R.error("清除离线任务失败", code=500)
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 清除离线任务失败: {e}")
        return R.error(f"清除离线任务失败: {str(e)}", code=500)


@router.post("/download")
def download_with_enhanced_features(
    url: str = Body(..., embed=True, description="百度网盘链接（支持分享链接、目录链接、秒传链接）"),
    output_dir: Optional[str] = Body(None, embed=True, description="输出目录"),
    need_video: bool = Body(False, embed=True, description="是否需要视频文件")
):
    """增强的下载功能（支持秒传链接）"""
    try:
        downloader = BaiduPanDownloader()
        result = downloader.download(url, output_dir, need_video=need_video)
        
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
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 下载失败: {e}")
        return R.error(f"下载失败: {str(e)}", code=500)


@router.post("/batch_download")
def batch_download_with_enhanced_features(
    url: str = Body(..., embed=True, description="百度网盘目录链接"),
    output_dir: Optional[str] = Body(None, embed=True, description="输出目录"),
    max_files: int = Body(10, embed=True, description="最大文件数量")
):
    """批量下载（支持目录和秒传链接）"""
    try:
        downloader = BaiduPanDownloader()
        results = downloader.batch_download(url, output_dir, max_files)
        
        results_data = []
        for result in results:
            result_dict = {
                "file_path": result.file_path,
                "title": result.title,
                "duration": result.duration,
                "platform": result.platform,
                "video_id": result.video_id,
                "raw_info": result.raw_info
            }
            results_data.append(result_dict)
        
        return R.success({
            "results": results_data,
            "total": len(results_data),
            "message": f"批量下载完成，成功处理 {len(results_data)} 个文件"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 批量下载失败: {e}")
        return R.error(f"批量下载失败: {str(e)}", code=500)


@router.post("/batch_rapid_upload")
def batch_rapid_upload_download(
    rapid_links: List[str] = Body(..., embed=True, description="秒传链接列表"),
    target_dir: str = Body("/", embed=True, description="目标目录")
):
    """批量秒传（集成下载器功能）"""
    try:
        downloader = BaiduPanDownloader()
        results = downloader.batch_rapid_upload(rapid_links, target_dir)
        
        results_data = []
        for result in results:
            result_dict = {
                "file_path": result.file_path,
                "title": result.title,
                "duration": result.duration,
                "platform": result.platform,
                "video_id": result.video_id,
                "raw_info": result.raw_info
            }
            results_data.append(result_dict)
        
        return R.success({
            "results": results_data,
            "successful": len(results_data),
            "total": len(rapid_links),
            "message": f"批量秒传完成: 成功 {len(results_data)}/{len(rapid_links)} 个"
        })
        
    except AuthRequiredException as e:
        logger.warning(f"⚠️ 百度网盘认证失败: {e}")
        return R.error("百度网盘认证已过期，请重新登录", code=401)
    except Exception as e:
        logger.error(f"❌ 批量秒传失败: {e}")
        return R.error(f"批量秒传失败: {str(e)}", code=500)