# app/routers/note.py
import json
import os
import uuid
from typing import Optional, Union
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, validator, field_validator
from dataclasses import asdict

from app.db.video_task_dao import get_task_by_video
from app.enmus.note_enums import DownloadQuality
from app.services.note import NoteGenerator, logger
from app.utils.response import ResponseWrapper as R
from app.utils.url_parser import extract_video_id, is_collection_url, extract_collection_videos, identify_platform
from app.validators.video_url_validator import is_supported_video_url
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from app.enmus.task_status_enums import TaskStatus
from app.models.note_api import StandardResponse, SingleVideoResponse, CollectionResponse, TaskInfo
from app.services.note import NoteGenerator
from app.utils.logger import get_logger
from app.core.task_queue import task_queue, TaskType, TaskStatus as QueueTaskStatus

# from app.services.downloader import download_raw_audio
# from app.services.whisperer import transcribe_audio

router = APIRouter()


class RecordRequest(BaseModel):
    video_id: str
    platform: str


class VideoRequest(BaseModel):
    video_url: str
    platform: str
    quality: DownloadQuality
    screenshot: Optional[bool] = False
    link: Optional[bool] = False
    model_name: str
    provider_id: str
    task_id: Optional[str] = None
    format: Optional[list] = []
    style: str = None
    extras: Optional[str]=None
    video_understanding: Optional[bool] = False
    video_interval: Optional[int] = 0
    grid_size: Optional[list] = []
    is_collection: Optional[bool] = False
    max_collection_videos: Optional[int] = 200

    @field_validator("video_url")
    def validate_supported_url(cls, v):
        url = str(v)
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            # 是网络链接，继续用原有平台校验
            if not is_supported_video_url(url):
                raise ValueError("暂不支持该视频平台或链接格式无效")

        return v


NOTE_OUTPUT_DIR = "note_results"
UPLOAD_DIR = "uploads"


def save_note_to_file(task_id: str, note):
    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    
    # 安全处理不同类型的note对象
    try:
        if hasattr(note, '__dataclass_fields__'):
            # 如果是dataclass实例，使用asdict
            note_data = asdict(note)
        elif isinstance(note, dict):
            # 如果已经是字典，直接使用
            note_data = note
        else:
            # 其他情况，转换为字典格式
            note_data = {"data": str(note), "type": type(note).__name__}
        
        with open(os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json"), "w", encoding="utf-8") as f:
            json.dump(note_data, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        # 如果序列化失败，保存错误信息
        error_data = {
            "error": f"序列化失败: {str(e)}",
            "note_type": type(note).__name__,
            "task_id": task_id
        }
        with open(os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json"), "w", encoding="utf-8") as f:
            json.dump(error_data, f, ensure_ascii=False, indent=2)


def run_note_task(task_id: str, video_url: str, platform: str, quality: DownloadQuality,
                  link: bool = False, screenshot: bool = False, model_name: str = None, provider_id: str = None,
                  _format: list = None, style: str = None, extras: str = None, video_understanding: bool = False,
                  video_interval=0, grid_size=[]
                  ):
    try:
        if not model_name or not provider_id:
            raise HTTPException(status_code=400, detail="请选择模型和提供者")

        note = NoteGenerator().generate(
            video_url=video_url,
            platform=platform,
            quality=quality,
            task_id=task_id,
            model_name=model_name,
            provider_id=provider_id,
            link=link,
            _format=_format,
            style=style,
            extras=extras,
            screenshot=screenshot
            , video_understanding=video_understanding,
            video_interval=video_interval,
            grid_size=grid_size
        )
        logger.info(f"Note generated: {task_id}")
        save_note_to_file(task_id, note)
    except Exception as e:
        save_note_to_file(task_id, {"error": str(e)})


@router.post('/delete_task')
def delete_task(data: RecordRequest):
    try:

        NoteGenerator().delete_note(video_id=data.video_id, platform=data.platform)
        return R.success(msg='删除成功')
    except Exception as e:
        return R.error(msg=e)


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_location = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_location, "wb+") as f:
        f.write(await file.read())

    # 假设你静态目录挂载了 /uploads
    return R.success({"url": f"/uploads/{file.filename}"})


@router.post("/generate_note")
async def generate_note(
    request: VideoRequest
) -> StandardResponse[Union[SingleVideoResponse, CollectionResponse]]:
    logger.info(f"🎬 收到生成笔记请求: {request.video_url}")
    logger.info(f"📊 请求参数: max_collection_videos={request.max_collection_videos}")
    
    try:
        # 识别视频平台
        platform = identify_platform(request.video_url)
        logger.info(f"🎯 识别到平台: {platform}")
        
        if not platform:
            logger.error("❌ 不支持的平台或无效的URL")
            raise HTTPException(status_code=400, detail="不支持的平台或无效的URL")

        # 检测是否为合集URL
        is_collection = is_collection_url(request.video_url, platform)
        logger.info(f"🔍 合集检测结果: {is_collection}")
        
        if is_collection:
            logger.info("🎬 进入合集处理分支")
            return await handle_collection_generation(request, platform)
        else:
            logger.info("📺 进入单视频处理分支")
            return await handle_single_video_generation(request, platform)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 生成笔记失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成笔记失败: {str(e)}")


async def handle_collection_generation(
    request: VideoRequest, 
    platform: str
) -> StandardResponse[CollectionResponse]:
    """处理合集生成请求"""
    logger.info(f"🎬 开始处理合集: {request.video_url}")
    logger.info(f"📊 合集参数: platform={platform}, max_videos={request.max_collection_videos}")
    
    try:
        # 对于其他合集URL，尝试快速提取视频列表
        logger.info("🔍 快速提取合集视频列表...")
        
        try:
            # 使用快速提取方法（有超时保护）
            videos = await extract_collection_videos_with_timeout(
                request.video_url, 
                platform, 
                request.max_collection_videos,
                timeout_seconds=8  # 8秒超时
            )
            
            if videos:
                logger.info(f"📹 快速提取成功，共 {len(videos)} 个视频")
                
                # 为每个视频创建任务
                task_list = []
                for video_url, title in videos:
                    task_data = {
                        'video_url': video_url,
                        'platform': platform,
                        'quality': request.quality,
                        'model_name': request.model_name,
                        'provider_id': request.provider_id,
                        'screenshot': request.screenshot,
                        'link': request.link,
                        'format': request.format,
                        'style': request.style,
                        'extras': request.extras,
                        'video_understanding': request.video_understanding,
                        'video_interval': request.video_interval,
                        'grid_size': request.grid_size,
                        'title': title
                    }
                    
                    task_id = task_queue.add_task(TaskType.SINGLE_VIDEO, task_data)
                    task_list.append(TaskInfo(
                        task_id=task_id,
                        video_url=video_url,
                        title=title
                    ))
                
                logger.info(f"✅ 已为 {len(task_list)} 个视频创建任务")
                
                response_data = CollectionResponse(
                    is_collection=True,
                    total_videos=len(videos),
                    created_tasks=len(task_list),
                    task_list=task_list,
                    message=f"已成功为合集中的 {len(task_list)} 个视频创建笔记生成任务"
                )
                
                return StandardResponse(
                    success=True,
                    data=response_data,
                    message=f"合集处理完成，共创建 {len(task_list)} 个任务"
                )
                
        except Exception as e:
            logger.warning(f"⚠️ 快速提取失败: {e}")
        
        # 如果快速提取失败，回退到异步处理
        logger.info("🔄 回退到异步处理模式")
        
        task_data = {
            'video_url': request.video_url,
            'platform': platform,
            'quality': request.quality,
            'model_name': request.model_name,
            'provider_id': request.provider_id,
            'screenshot': request.screenshot,
            'link': request.link,
            'format': request.format,
            'style': request.style,
            'extras': request.extras,
            'video_understanding': request.video_understanding,
            'video_interval': request.video_interval,
            'grid_size': request.grid_size,
            'max_collection_videos': request.max_collection_videos
        }
        
        collection_task_id = task_queue.add_task(TaskType.COLLECTION, task_data)
        logger.info(f"✅ 合集任务已添加到队列: {collection_task_id}")
        
        response_data = CollectionResponse(
            is_collection=True,
            total_videos=0,
            created_tasks=0,
            task_list=[],
            message="合集检测成功，正在后台解析和创建任务，请稍等片刻查看任务列表"
        )
        
        return StandardResponse(
            success=True,
            data=response_data,
            message="合集处理已开始，正在后台解析视频列表"
        )
        
    except Exception as e:
        logger.error(f"❌ 处理合集失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理合集失败: {str(e)}")


async def handle_single_video_generation(
    request: VideoRequest, 
    platform: str
) -> StandardResponse[SingleVideoResponse]:
    """处理单视频生成请求"""
    logger.info(f"📺 开始处理单视频: {request.video_url}")
    logger.info(f"📊 单视频参数: platform={platform}")
    
    try:
        # 准备任务数据
        task_data = {
            'video_url': request.video_url,
            'platform': platform,
            'quality': request.quality,
            'model_name': request.model_name,
            'provider_id': request.provider_id,
            'screenshot': request.screenshot,
            'link': request.link,
            'format': request.format,
            'style': request.style,
            'extras': request.extras,
            'video_understanding': request.video_understanding,
            'video_interval': request.video_interval,
            'grid_size': request.grid_size
        }
        
        # 添加单视频任务到队列
        task_id = task_queue.add_task(TaskType.SINGLE_VIDEO, task_data)
        logger.info(f"✅ 单视频任务已添加到队列: {task_id}")
        
        # 返回单视频处理结果
        response_data = SingleVideoResponse(
            is_collection=False,
            task_id=task_id
        )
        
        return StandardResponse(
            success=True,
            data=response_data,
            message="笔记生成任务已创建"
        )
        
    except Exception as e:
        logger.error(f"❌ 处理单视频失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理单视频失败: {str(e)}")


@router.get("/task_status/{task_id}")
def get_task_status(task_id: str):
    # 首先检查任务队列中的状态
    queue_task = task_queue.get_task_status(task_id)
    if queue_task:
        # 删除频繁的状态查询日志，减少日志输出
        # logger.info(f"🔍 从任务队列获取状态: {task_id} -> {queue_task.status.value}")
        
        # 映射任务队列状态到原有状态
        status_mapping = {
            QueueTaskStatus.PENDING: TaskStatus.PENDING.value,
            QueueTaskStatus.RUNNING: TaskStatus.RUNNING.value,
            QueueTaskStatus.SUCCESS: TaskStatus.SUCCESS.value,
            QueueTaskStatus.FAILED: TaskStatus.FAILED.value
        }
        
        mapped_status = status_mapping.get(queue_task.status, TaskStatus.PENDING.value)
        
        if queue_task.status == QueueTaskStatus.FAILED:
            return R.error(queue_task.error_message or "任务失败", code=500)
        elif queue_task.status == QueueTaskStatus.SUCCESS:
            # 任务成功，尝试读取结果文件
            result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")
            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8") as f:
                    result_content = json.load(f)
                return R.success({
                    "status": mapped_status,
                    "result": result_content,
                    "message": "任务完成",
                    "task_id": task_id
                })
            else:
                return R.success({
                    "status": TaskStatus.PENDING.value,
                    "message": "任务完成，但结果文件未找到",
                    "task_id": task_id
                })
        else:
            # PENDING 或 RUNNING 状态
            message = "任务排队中" if queue_task.status == QueueTaskStatus.PENDING else "任务处理中"
            return R.success({
                "status": mapped_status,
                "message": message,
                "task_id": task_id
            })
    
    # 任务队列中找不到，检查文件系统
    status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
    result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")

    # 优先读状态文件
    if os.path.exists(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            status_content = json.load(f)

        status = status_content.get("status")
        message = status_content.get("message", "")

        if status == TaskStatus.SUCCESS.value:
            # 成功状态的话，继续读取最终笔记内容
            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8") as rf:
                    result_content = json.load(rf)
                return R.success({
                    "status": status,
                    "result": result_content,
                    "message": message,
                    "task_id": task_id
                })
            else:
                # 理论上不会出现，保险处理
                return R.success({
                    "status": TaskStatus.PENDING.value,
                    "message": "任务完成，但结果文件未找到",
                    "task_id": task_id
                })

        if status == TaskStatus.FAILED.value:
            return R.error(message or "任务失败", code=500)

        # 处理中状态
        return R.success({
            "status": status,
            "message": message,
            "task_id": task_id
        })

    # 没有状态文件，但有结果
    if os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as f:
            result_content = json.load(f)
        return R.success({
            "status": TaskStatus.SUCCESS.value,
            "result": result_content,
            "task_id": task_id
        })

    # 什么都没有，默认PENDING
    return R.success({
        "status": TaskStatus.PENDING.value,
        "message": "任务排队中",
        "task_id": task_id
    })


@router.get("/image_proxy")
async def image_proxy(request: Request, url: str):
    headers = {
        "Referer": "https://www.bilibili.com/",
        "User-Agent": request.headers.get("User-Agent", ""),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="图片获取失败")

            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return StreamingResponse(
                resp.aiter_bytes(),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  # ✅ 缓存一天
                    "Content-Type": content_type,
                }
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 任务处理逻辑已移至 app/core/task_queue.py 中的 TaskQueue 类

import asyncio
import threading
from typing import List, Tuple

async def extract_collection_videos_with_timeout(
    url: str, 
    platform: str, 
    max_videos: int = 50,
    timeout_seconds: int = 8
) -> List[Tuple[str, str]]:
    """
    带超时的合集视频提取函数
    """
    logger.info(f"🕒 开始快速提取合集视频，超时限制: {timeout_seconds}秒")
    
    result = {"videos": [], "error": None}
    
    def extract_thread():
        try:
            # 调用原有的提取函数
            videos = extract_collection_videos(url, platform, max_videos)
            result["videos"] = videos
            
        except Exception as e:
            result["error"] = e
    
    # 在线程中执行提取
    thread = threading.Thread(target=extract_thread)
    thread.daemon = True
    thread.start()
    
    # 等待超时
    thread.join(timeout=timeout_seconds)
    
    if thread.is_alive():
        logger.warning(f"⚠️ 提取超时 ({timeout_seconds}秒)，放弃快速提取")
        return []
    
    if result["error"]:
        logger.warning(f"⚠️ 提取出错: {result['error']}")
        return []
    
    logger.info(f"✅ 快速提取成功，获得 {len(result['videos'])} 个视频")
    return result["videos"]

@router.get("/queue_status")
def get_queue_status():
    """获取任务队列状态"""
    try:
        all_tasks = task_queue.get_all_tasks()
        
        queue_info = {
            "total_tasks": len(all_tasks),
            "pending_tasks": len([t for t in all_tasks.values() if t.status == QueueTaskStatus.PENDING]),
            "running_tasks": len([t for t in all_tasks.values() if t.status == QueueTaskStatus.RUNNING]),
            "completed_tasks": len([t for t in all_tasks.values() if t.status == QueueTaskStatus.SUCCESS]),
            "failed_tasks": len([t for t in all_tasks.values() if t.status == QueueTaskStatus.FAILED]),
            "tasks": []
        }
        
        # 返回任务详情
        for task in all_tasks.values():
            task_info = {
                "task_id": task.task_id,
                "task_type": task.task_type.value,
                "status": task.status.value,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
                "video_url": task.data.get('video_url', ''),
                "title": task.data.get('title', '未知标题'),
                "error_message": task.error_message
            }
            queue_info["tasks"].append(task_info)
        
        return R.success(queue_info)
        
    except Exception as e:
        logger.error(f"❌ 获取队列状态失败: {e}")
        return R.error(f"获取队列状态失败: {str(e)}")

@router.get("/tasks/recent")
def get_recent_tasks(limit: int = 50):
    """获取最近的任务列表（用于前端任务列表显示）"""
    try:
        all_tasks = task_queue.get_all_tasks()
        
        # 按创建时间排序，最新的在前
        sorted_tasks = sorted(all_tasks.values(), key=lambda x: x.created_at or 0, reverse=True)
        
        task_list = []
        for task in sorted_tasks[:limit]:
            # 映射队列状态到前端状态
            frontend_status = "PENDING"
            if task.status == QueueTaskStatus.RUNNING:
                frontend_status = "RUNNING"
            elif task.status == QueueTaskStatus.SUCCESS:
                frontend_status = "SUCCESS"
            elif task.status == QueueTaskStatus.FAILED:
                frontend_status = "FAILED"
            
            task_info = {
                "task_id": task.task_id,
                "video_url": task.data.get('video_url', ''),
                "title": task.data.get('title', '未知标题'),
                "platform": task.data.get('platform', ''),
                "status": frontend_status,
                "created_at": task.created_at,
                "error_message": task.error_message
            }
            task_list.append(task_info)
        
        return R.success({
            "tasks": task_list,
            "total": len(sorted_tasks)
        })
        
    except Exception as e:
        logger.error(f"❌ 获取最近任务失败: {e}")
        return R.error(f"获取最近任务失败: {str(e)}")
