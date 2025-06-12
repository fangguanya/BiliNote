# app/routers/note.py
import json
import os
import traceback
import uuid
import time
import glob
import asyncio
from typing import Optional, Union, List, Tuple
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, validator, field_validator
from dataclasses import asdict

from app.db.video_task_dao import get_task_by_video
from app.enmus.note_enums import DownloadQuality
from app.services.note import NoteGenerator, logger, NoteService
from app.utils.response import ResponseWrapper as R
from app.utils.url_parser import extract_video_id, is_collection_url, extract_collection_videos_async, identify_platform
from app.utils.task_utils import save_original_request_data, load_original_request_data
from app.validators.video_url_validator import is_supported_video_url
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from app.enmus.task_status_enums import TaskStatus
from app.models.note_api import StandardResponse, SingleVideoResponse, CollectionResponse, TaskInfo
from app.core.task_queue import TaskType, TaskStatus as QueueTaskStatus, task_queue
from app.core.exception_handlers import wrap_request_handler, record_request_error
from app.utils.baidu_utils import delete_baidu_pan_file

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
    max_collection_videos: Optional[int] = 400
    auto_save_notion: Optional[bool] = True
    auto_detect_collection: Optional[bool] = True  # 新增：自动识别合集开关

    @field_validator("video_url")
    def validate_supported_url(cls, v):
        url = str(v)
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            # 是网络链接，继续用原有平台校验
            if not is_supported_video_url(url):
                raise ValueError("暂不支持该视频平台或链接格式无效")

        return v


NOTE_OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "note_results"))
UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads"))


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

        # 检测是否为合集URL（根据auto_detect_collection开关决定）
        is_collection = False
        if request.auto_detect_collection:
            is_collection = is_collection_url(request.video_url, platform)
            logger.info(f"🔍 合集检测结果: {is_collection} (自动识别开关: 开)")
        else:
            logger.info(f"🔍 合集检测被跳过 (自动识别开关: 关)")
        
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
        logger.info("🔍 [异步] 快速提取合集视频列表...")
        videos = None
        
        try:
            # 使用新的异步提取函数，并设置超时
            videos = await asyncio.wait_for(
                extract_collection_videos_async(
                    request.video_url, 
                    platform, 
                    request.max_collection_videos
                ),
                timeout=25.0  # 设置25秒超时
            )
            
            if videos:
                logger.info(f"📹 [异步] 快速提取成功，共 {len(videos)} 个视频")
                
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
                
        except asyncio.TimeoutError:
            logger.warning("⚠️ 快速提取超时 (25秒)，将回退到后台异步处理。")
            # 超时后 videos 会是 None, 流程将自然进入下面的回退逻辑
        except Exception as e:
            logger.warning(f"⚠️ [异步] 快速提取失败: {e}", exc_info=True)
            # 同样回退到后台异步处理
        
        # 如果快速提取失败、超时或没有返回视频，则回退到异步处理
        logger.info("🔄 回退到后台异步处理模式 (创建单个合集任务)")
        
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
            message="合集视频列表解析耗时较长，已转为后台任务处理，请稍后在任务列表中查看进度。"
        )
        
        return StandardResponse(
            success=True,
            data=response_data,
            message="合集处理已转为后台任务"
        )
        
    except Exception as e:
        logger.error(f"❌ 处理合集失败: {e}", exc_info=True)
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

@router.post("/retry_task/{task_id}")
def retry_task(task_id: str):
    """重试失败的任务"""
    try:
        # 首先检查任务队列中是否存在该任务
        queue_task = task_queue.get_task_status(task_id)
        if queue_task:
            # 在任务队列中重试
            success = task_queue.retry_task(task_id)
            if success:
                logger.info(f"✅ 任务重试成功: {task_id}")
                return R.success({
                    "message": "任务已重新提交，请等待处理",
                    "task_id": task_id
                })
            else:
                return R.error("任务重试失败，请检查任务状态")
        
        # 任务队列中没有，检查文件系统中的任务
        status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
        if os.path.exists(status_path):
            with open(status_path, "r", encoding="utf-8") as f:
                status_content = json.load(f)
            
            status = status_content.get("status")
            if status == TaskStatus.FAILED.value:
                # 从文件系统中读取原始任务数据并重新提交
                # 这需要有存储原始请求参数的机制
                logger.warning(f"⚠️ 任务 {task_id} 在文件系统中，但无法直接重试。建议重新提交新任务。")
                return R.error("该任务无法直接重试，请重新提交新任务")
            else:
                return R.error(f"任务状态不是失败状态，无法重试 (当前状态: {status})")
        
        return R.error("任务不存在")
        
    except Exception as e:
        logger.error(f"❌ 重试任务失败: {e}")
        return R.error(f"重试任务失败: {str(e)}")

@router.post("/batch_retry_failed")
def batch_retry_failed_tasks():
    """批量重试所有失败的任务"""
    try:
        result = task_queue.batch_retry_failed_tasks()
        logger.info(f"✅ 批量重试失败任务完成: {result}")
        
        if result["retried_count"] > 0:
            return R.success({
                "retried_count": result["retried_count"],
                "total_failed": result["total_failed"],
                "message": result["message"]
            })
        else:
            return R.success({
                "retried_count": 0,
                "total_failed": 0,
                "message": "没有需要重试的失败任务"
            })
        
    except Exception as e:
        logger.error(f"❌ 批量重试失败任务出错: {e}")
        return R.error(f"批量重试失败: {str(e)}")

@router.post("/batch_retry_non_success")
def batch_retry_non_success_tasks():
    """批量重试所有非成功状态的任务（包括PENDING、RUNNING、FAILED）"""
    try:
        # 首先尝试重试队列中的任务
        queue_result = task_queue.batch_retry_non_success_tasks()
        logger.info(f"✅ 队列批量重试完成: {queue_result}")
        
        # 如果队列中没有需要重试的任务，尝试从文件系统重建
        if queue_result["retried_count"] == 0:
            logger.info("🔍 队列为空，尝试从文件系统重建需要重试的任务")
            
            # 扫描所有状态文件，查找失败的任务
            rebuilt_count = 0
            status_files = glob.glob(os.path.join(NOTE_OUTPUT_DIR, "*.status.json"))
            
            for status_file in status_files:
                try:
                    task_id = os.path.basename(status_file).replace(".status.json", "")
                    
                    # 检查任务是否已在队列中
                    if task_queue.get_task_status(task_id):
                        continue
                    
                    with open(status_file, "r", encoding="utf-8") as f:
                        status_content = json.load(f)
                    
                    status = status_content.get("status")
                    if status and status != TaskStatus.SUCCESS.value:
                        # 尝试重建任务
                        success = rebuild_task_from_files(task_id)
                        if success:
                            rebuilt_count += 1
                            logger.info(f"✅ 成功重建任务: {task_id}")
                        else:
                            logger.warning(f"⚠️ 重建任务失败: {task_id}")
                            
                except Exception as e:
                    logger.error(f"❌ 处理状态文件失败 {status_file}: {e}")
            
            if rebuilt_count > 0:
                logger.info(f"🔄 从文件系统重建了 {rebuilt_count} 个任务")
                return R.success({
                    "retried_count": rebuilt_count,
                    "total_non_success": rebuilt_count,
                    "rebuilt_from_files": True,
                    "message": f"从文件系统重建并重试了 {rebuilt_count} 个任务"
                })
        
        # 返回原始队列重试结果
        if queue_result["retried_count"] > 0:
            return R.success({
                "retried_count": queue_result["retried_count"],
                "total_non_success": queue_result["total_non_success"],
                "pending_count": queue_result["pending_count"],
                "running_count": queue_result["running_count"],
                "failed_count": queue_result["failed_count"],
                "message": queue_result["message"]
            })
        else:
            return R.success({
                "retried_count": 0,
                "total_non_success": 0,
                "message": "没有需要重试的非成功任务"
            })
        
    except Exception as e:
        logger.error(f"❌ 批量重试非成功任务出错: {e}")
        return R.error(f"批量重试非成功任务失败: {str(e)}")

def rebuild_task_from_files(task_id: str) -> bool:
    """从文件系统重建任务"""
    try:
        from app.core.task_queue import TaskType
        from app.enmus.note_enums import DownloadQuality
        
        # 检查音频metadata文件（分离文件模式）
        audio_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_audio.json")
        result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")
        
        # 首先尝试从音频metadata文件获取信息
        if os.path.exists(audio_path):
            try:
                with open(audio_path, "r", encoding="utf-8") as f:
                    audio_data = json.load(f)
                
                video_url = audio_data.get("file_path", "")
                platform = audio_data.get("platform", "")
                title = audio_data.get("title", "未知标题")
                
                if video_url and platform:
                    try:
                        task_data = {
                            'video_url': video_url,
                            'platform': platform,
                            'quality': DownloadQuality.fast,
                            'model_name': 'gpt-4o-mini',
                            'provider_id': 'openai',
                            'screenshot': False,
                            'link': False,
                            'format': [],
                            'style': '简洁',
                            'extras': None,
                            'video_understanding': False,
                            'video_interval': 0,
                            'grid_size': [],
                            'title': title
                        }
                        
                        task_queue.add_task(
                            task_type=TaskType.SINGLE_VIDEO, 
                            data=task_data,
                            task_id=task_id
                        )
                        return True
                    except Exception as task_error:
                        logger.error(f"❌ 从音频metadata创建任务失败: {task_id}, {task_error}")
                        # 创建任务失败，但继续尝试清空重置
                        return clear_and_reset_task(task_id)
                    
            except Exception as e:
                logger.error(f"❌ 从音频metadata重建任务失败: {task_id}, {e}")
                # 读取音频metadata文件失败，调用删除老记录重新队列执行
                logger.info(f"🔄 音频metadata文件读取失败，尝试清空重置任务: {task_id}")
                return clear_and_reset_task(task_id)
        
        # 如果音频文件不存在，尝试从主结果文件读取
        if os.path.exists(result_path):
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    result_data = json.load(f)
                
                # 检查是否为错误文件
                if "error" in result_data:
                    logger.warning(f"⚠️ 发现错误文件，尝试清空重置任务: {task_id}")
                    return clear_and_reset_task(task_id, result_data)
                
                if "audioMeta" in result_data:
                    audio_meta = result_data.get("audioMeta", {})
                    video_url = audio_meta.get("file_path", "")
                    platform = audio_meta.get("platform", "")
                    title = audio_meta.get("title", "未知标题")
                    
                    if video_url and platform:
                        try:
                            task_data = {
                                'video_url': video_url,
                                'platform': platform,
                                'quality': DownloadQuality.fast,
                                'model_name': 'gpt-4o-mini',
                                'provider_id': 'openai',
                                'screenshot': False,
                                'link': False,
                                'format': [],
                                'style': '简洁',
                                'extras': None,
                                'video_understanding': False,
                                'video_interval': 0,
                                'grid_size': [],
                                'title': title
                            }
                            
                            task_queue.add_task(
                                task_type=TaskType.SINGLE_VIDEO, 
                                data=task_data,
                                task_id=task_id
                            )
                            return True
                        except Exception as task_error:
                            logger.error(f"❌ 从结果文件创建任务失败: {task_id}, {task_error}")
                            # 创建任务失败，但继续尝试清空重置
                            return clear_and_reset_task(task_id, result_data)
                else:
                    # 结果文件格式不正确，调用删除老记录重新队列执行
                    logger.warning(f"⚠️ 结果文件格式不正确: {task_id}")
                    logger.info(f"🔄 结果文件格式不正确，尝试清空重置任务: {task_id}")
                    return clear_and_reset_task(task_id, result_data)
                        
            except Exception as e:
                logger.error(f"❌ 从结果文件重建任务失败: {task_id}, {e}")
                # 读取结果文件失败，调用删除老记录重新队列执行
                logger.info(f"🔄 结果文件读取失败，尝试清空重置任务: {task_id}")
                return clear_and_reset_task(task_id)
        else:
            # 未找到任务相关文件，调用删除老记录重新队列执行
            logger.warning(f"⚠️ 未找到任务相关文件: {task_id}")
            logger.info(f"🔄 未找到任务相关文件，尝试清空重置任务: {task_id}")
            return clear_and_reset_task(task_id)
        
        # 如果都无法重建，尝试清空重置
        logger.warning(f"⚠️ 无法重建任务，尝试清空重置: {task_id}")
        return clear_and_reset_task(task_id)
        
    except Exception as e:
        logger.error(f"❌ 重建任务出错: {task_id}, {e}")
        return False

def clear_and_reset_task(task_id: str, error_data: dict = None) -> bool:
    """清空任务相关文件并尝试重置任务"""
    try:
        from app.core.task_queue import TaskType
        from app.enmus.note_enums import DownloadQuality
        
        logger.info(f"🧹 开始清空重置任务: {task_id}")
        
        # 尝试从多个来源提取原始信息
        original_url = None
        original_platform = None
        original_title = "重置任务"
        
        # 1. 优先从持久化的原始请求数据中提取
        request_file_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.request.json")
        if os.path.exists(request_file_path):
            try:
                with open(request_file_path, "r", encoding="utf-8") as f:
                    request_data = json.load(f)
                
                original_request = request_data.get("original_request", {})
                if original_request:
                    original_url = original_request.get("video_url")
                    original_platform = original_request.get("platform")
                    original_title = original_request.get("title", "重置任务")
                    
                    if original_url:
                        logger.info(f"✅ 从持久化请求数据中找到原始URL: {original_url}")
                        
            except Exception as e:
                logger.warning(f"⚠️ 读取持久化请求数据失败: {e}")
        
        # 2. 如果持久化数据中没有找到，尝试从错误数据中提取
        if not original_url and error_data and isinstance(error_data, dict):
            # 尝试从错误信息中提取原始URL
            if "url" in error_data:
                original_url = error_data["url"]
            elif "video_url" in error_data:
                original_url = error_data["video_url"]
            elif "request_data" in error_data:
                request_data = error_data["request_data"]
                if isinstance(request_data, dict):
                    original_url = request_data.get("video_url")
                    original_platform = request_data.get("platform")
                    original_title = request_data.get("title", "重置任务")
            # 尝试从audioMeta中提取
            elif "audioMeta" in error_data:
                audio_meta = error_data["audioMeta"]
                if isinstance(audio_meta, dict):
                    file_path = audio_meta.get("file_path", "")
                    video_id = audio_meta.get("video_id", "")
                    original_platform = audio_meta.get("platform", "")
                    original_title = audio_meta.get("title", "重置任务")
                    
                    # 如果是BV号，转换为B站URL
                    if video_id and video_id.startswith("BV"):
                        original_url = f"https://www.bilibili.com/video/{video_id}"
                        original_platform = "bilibili"
                    elif file_path and "http" in file_path:
                        original_url = file_path
        
        # 3. 如果错误数据中没有找到，尝试从任务状态文件中提取
        if not original_url:
            status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
            if os.path.exists(status_path):
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        status_data = json.load(f)
                    
                    # 从状态文件中提取原始信息
                    if "original_request" in status_data:
                        orig_req = status_data["original_request"]
                        original_url = orig_req.get("video_url")
                        original_platform = orig_req.get("platform")
                        original_title = orig_req.get("title", "重置任务")
                except Exception as e:
                    logger.warning(f"⚠️ 读取状态文件失败: {e}")
        
        # 4. 如果还是没有找到，尝试从音频metadata文件中提取
        if not original_url:
            audio_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_audio.json")
            if os.path.exists(audio_path):
                try:
                    with open(audio_path, "r", encoding="utf-8") as f:
                        audio_data = json.load(f)
                    
                    file_path = audio_data.get("file_path", "")
                    video_id = audio_data.get("video_id", "")
                    original_platform = audio_data.get("platform", "")
                    original_title = audio_data.get("title", "重置任务")
                    raw_info = audio_data.get("raw_info", {})
                    
                    # 优先检查 raw_info 中是否有原始URL信息
                    if raw_info and isinstance(raw_info, dict):
                        if "webpage_url" in raw_info:
                            original_url = raw_info["webpage_url"]
                            logger.info(f"🔍 从raw_info中找到原始URL: {original_url}")
                        elif "original_url" in raw_info:
                            original_url = raw_info["original_url"]
                            logger.info(f"🔍 从raw_info中找到原始URL: {original_url}")
                    
                    # 如果 raw_info 中没有，尝试用 video_id 重构
                    if not original_url and video_id:
                        if video_id.startswith("BV"):
                            # 检查 video_id 中是否包含分P信息（例如：BV1pwj2zxEL9_p64）
                            if "_p" in video_id:
                                base_bv, p_part = video_id.split("_p", 1)
                                try:
                                    p_num = int(p_part)
                                    original_url = f"https://www.bilibili.com/video/{base_bv}?p={p_num}"
                                    logger.info(f"🔄 重构分P视频URL: {video_id} -> {original_url}")
                                except ValueError:
                                    # 分P编号无效，使用基础BV号
                                    original_url = f"https://www.bilibili.com/video/{base_bv}"
                                    logger.info(f"🔄 重构视频URL (忽略无效分P): {video_id} -> {original_url}")
                            else:
                                # 普通BV号
                                original_url = f"https://www.bilibili.com/video/{video_id}"
                                logger.info(f"🔄 重构视频URL: {video_id} -> {original_url}")
                            original_platform = "bilibili"
                        else:
                            logger.warning(f"⚠️ 无法识别的video_id格式: {video_id}")
                    
                    # 最后检查file_path是否包含HTTP URL（用于其他平台）
                    if not original_url and file_path and "http" in file_path:
                        original_url = file_path
                        logger.info(f"🔄 使用file_path作为URL: {file_path}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ 读取音频metadata文件失败: {e}")
        
        # 清空相关文件（保留原始请求数据文件）
        files_to_clean = [
            f"{task_id}.json",          # 结果文件
            f"{task_id}.status.json",   # 状态文件
            # f"{task_id}.request.json",  # 🔒 保留原始请求数据文件，不删除
            f"{task_id}_audio.json",    # 音频metadata文件
            f"{task_id}_audio.wav",     # 音频文件
            f"{task_id}_audio.mp3",     # 音频文件
            f"{task_id}.wav",           # 音频文件
            f"{task_id}.mp3",           # 音频文件
        ]
        
        cleaned_files = []
        for filename in files_to_clean:
            file_path = os.path.join(NOTE_OUTPUT_DIR, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    cleaned_files.append(filename)
                    logger.info(f"🗑️ 已删除文件: {filename}")
                except Exception as e:
                    logger.warning(f"⚠️ 删除文件失败 {filename}: {e}")
        
        logger.info(f"🧹 清理完成，删除了 {len(cleaned_files)} 个文件")
        
        # 如果找到了原始URL，重新创建任务
        if original_url:
            # 尝试识别平台
            if not original_platform:
                if "bilibili.com" in original_url or "b23.tv" in original_url:
                    original_platform = "bilibili"
                elif "youtube.com" in original_url or "youtu.be" in original_url:
                    original_platform = "youtube"
                else:
                    original_platform = "unknown"
            
            logger.info(f"🔄 使用原始URL重新创建任务: {original_url}")
            
            try:
                task_data = {
                    'video_url': original_url,
                    'platform': original_platform,
                    'quality': DownloadQuality.fast,
                    'model_name': 'gpt-4o-mini',
                    'provider_id': 'openai',
                    'screenshot': False,
                    'link': False,
                    'format': [],
                    'style': '简洁',
                    'extras': None,
                    'video_understanding': False,
                    'video_interval': 0,
                    'grid_size': [],
                    'title': original_title
                }
                
                # 使用原task_id重新创建任务
                new_task_id = task_queue.add_task(
                    task_type=TaskType.SINGLE_VIDEO, 
                    data=task_data,
                    task_id=task_id
                )
                
                logger.info(f"✅ 任务队列添加成功: {task_id}")
                
                # 更新原始请求数据文件（保存新的任务数据）
                try:
                    updated_request_data = {
                        "task_id": task_id,
                        "created_at": time.time(),
                        "created_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                        "reset_count": 1,  # 标记这是重置任务
                        "original_request": {
                            "video_url": original_url,
                            "platform": original_platform,
                            "title": original_title,
                            "quality": task_data.get('quality', DownloadQuality.fast),
                            "model_name": task_data.get('model_name', 'gpt-4o-mini'),
                            "provider_id": task_data.get('provider_id', 'openai'),
                            "screenshot": task_data.get('screenshot', False),
                            "link": task_data.get('link', False),
                            "format": task_data.get('format', []),
                            "style": task_data.get('style', '简洁'),
                            "extras": task_data.get('extras', None),
                            "video_understanding": task_data.get('video_understanding', False),
                            "video_interval": task_data.get('video_interval', 0),
                            "grid_size": task_data.get('grid_size', [])
                        }
                    }
                    
                    request_file_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.request.json")
                    with open(request_file_path, "w", encoding="utf-8") as f:
                        json.dump(updated_request_data, f, ensure_ascii=False, indent=2)
                    
                    logger.info(f"📝 已更新原始请求数据文件: {task_id}")
                    
                except Exception as save_error:
                    logger.warning(f"⚠️ 更新原始请求数据文件失败: {save_error}")
                
                logger.info(f"✅ 任务清空重置成功: {task_id} -> 新URL: {original_url}")
                return True
                
            except Exception as task_create_error:
                logger.error(f"❌ 创建任务神奇的失败: {task_id}, {task_create_error}, {traceback.format_exc()}")
                logger.warning(f"⚠️ 任务创建失败但文件已清空，继续处理: {task_id}")
                # 任务创建失败，但文件清空成功，也认为是部分成功
                return len(cleaned_files) > 0
        else:
            logger.warning(f"⚠️ 无法找到原始URL，只能清空文件: {task_id}， {error_data}")
            # 即使无法重新创建，清空文件也算成功
            return len(cleaned_files) > 0
        
    except Exception as e:
        logger.error(f"❌ 清空重置任务失败: {task_id}, {e}")
        return False

class ValidateTasksRequest(BaseModel):
    """验证任务请求模型"""
    task_ids: List[str]

@router.post("/validate_tasks")
def validate_tasks(request: ValidateTasksRequest):
    """验证前端任务ID列表，返回真正需要重试的任务状态"""
    try:
        task_ids = request.task_ids
        validation_results = []
        
        for task_id in task_ids:
            # 检查任务队列中的状态
            queue_task = task_queue.get_task_status(task_id)
            if queue_task:
                # 任务在队列中，返回队列状态
                validation_results.append({
                    "task_id": task_id,
                    "exists_in_queue": True,
                    "status": queue_task.status.value,
                    "needs_retry": queue_task.status != QueueTaskStatus.SUCCESS,
                    "error_message": queue_task.error_message
                })
            else:
                # 任务不在队列中，检查文件系统
                status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
                result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")
                
                if os.path.exists(status_path):
                    try:
                        with open(status_path, "r", encoding="utf-8") as f:
                            status_content = json.load(f)
                        status = status_content.get("status")
                        validation_results.append({
                            "task_id": task_id,
                            "exists_in_queue": False,
                            "status": status,
                            "needs_retry": status != TaskStatus.SUCCESS.value,
                            "error_message": status_content.get("message")
                        })
                    except Exception as e:
                        validation_results.append({
                            "task_id": task_id,
                            "exists_in_queue": False,
                            "status": "UNKNOWN",
                            "needs_retry": True,
                            "error_message": f"读取状态文件失败: {str(e)}"
                        })
                elif os.path.exists(result_path):
                    # 只有结果文件，说明任务已完成
                    validation_results.append({
                        "task_id": task_id,
                        "exists_in_queue": False,
                        "status": TaskStatus.SUCCESS.value,
                        "needs_retry": False,
                        "error_message": None
                    })
                else:
                    # 什么都没有，任务不存在
                    validation_results.append({
                        "task_id": task_id,
                        "exists_in_queue": False,
                        "status": "NOT_FOUND",
                        "needs_retry": False,
                        "error_message": "任务不存在"
                    })
        
        # 统计结果
        needs_retry_count = len([r for r in validation_results if r["needs_retry"]])
        total_tasks = len(validation_results)
        
        logger.info(f"✅ 任务验证完成: 总数={total_tasks}, 需重试={needs_retry_count}")
        
        return R.success({
            "validation_results": validation_results,
            "total_tasks": total_tasks,
            "needs_retry_count": needs_retry_count,
            "message": f"验证完成：{total_tasks}个任务中有{needs_retry_count}个需要重试"
        })
        
    except Exception as e:
        logger.error(f"❌ 验证任务状态出错: {e}")
        return R.error(f"验证任务状态失败: {str(e)}")

class ForceRetryRequest(BaseModel):
    """强制重试请求模型"""
    model_name: Optional[str] = None
    provider_id: Optional[str] = None
    style: Optional[str] = None
    format: Optional[list] = None
    video_understanding: Optional[bool] = None
    video_interval: Optional[int] = None

class ForceRetryAllRequest(BaseModel):
    """强制全部重试请求模型"""
    task_ids: List[str]
    config: Optional[dict] = {}

@router.post("/force_retry_all")
def force_retry_all(request: ForceRetryAllRequest):
    """
    强制重试所有任务，可选择使用新的配置覆盖。
    """
    try:
        logger.info(f"⚡️ API层: 接收到强制重试所有任务请求 for {len(request.task_ids)} tasks")
        
        config = request.config
        logger.info(f"   - 提供的覆盖配置: {config}")

        note_service = NoteService()
        result = note_service.force_retry_all(task_ids=request.task_ids, override_data=config)
        
        return R.success(data=result)
        
    except Exception as e:
        logger.error(f"❌ 强制重试所有任务失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/force_retry_task/{task_id}")
def force_retry_task(task_id: str, request: Optional[ForceRetryRequest] = None):
    """强制重试单个任务（包括成功状态的任务）"""
    try:
        from app.core.task_queue import TaskStatus as QueueTaskStatus, TaskType
        
        # 首先检查任务队列中是否存在该任务
        queue_task = task_queue.get_task_status(task_id)
        if queue_task:
            # 强制重试，不检查状态
            with task_queue._lock:
                task = task_queue.tasks.get(task_id)
                if task:
                    # 如果有新的配置，更新任务数据
                    if request and hasattr(request, 'model_name') and request.model_name:
                        task.data['model_name'] = request.model_name
                    if request and hasattr(request, 'provider_id') and request.provider_id:
                        task.data['provider_id'] = request.provider_id
                    if request and hasattr(request, 'style') and request.style:
                        task.data['style'] = request.style
                    if request and hasattr(request, 'format') and request.format:
                        task.data['format'] = request.format
                    if request and hasattr(request, 'video_understanding') and request.video_understanding is not None:
                        task.data['video_understanding'] = request.video_understanding
                    if request and hasattr(request, 'video_interval') and request.video_interval is not None:
                        task.data['video_interval'] = request.video_interval
                    
                    # 重置任务状态
                    task.status = QueueTaskStatus.PENDING
                    task.started_at = None
                    task.completed_at = None
                    task.error_message = None
                    task.result = None
                    
                    # 重新提交到队列
                    task_queue.task_queue.put(task)
                    
                    logger.info(f"✅ 强制重试任务成功: {task_id}")
                    return R.success({
                        "message": "任务已强制重新提交，请等待处理",
                        "task_id": task_id
                    })
                else:
                    return R.error("任务不存在")
        
        # 任务不在队列中，优先尝试从持久化的原始请求数据重建
        logger.info(f"🔍 任务不在队列中，尝试从持久化的原始请求数据重建: {task_id}")
        
        try:
            # 加载持久化的原始请求数据
            original_request_data = load_original_request_data(task_id)
            
            if original_request_data:
                video_url = original_request_data.get('video_url')
                platform = original_request_data.get('platform')
                title = original_request_data.get('title', '未知标题')
                
                if video_url and platform:
                    try:
                        from app.enmus.note_enums import DownloadQuality
                        
                        # 构建任务数据，使用持久化数据，可能会被请求中的新配置覆盖
                        task_data = {
                            'video_url': video_url,
                            'platform': platform,
                            'quality': original_request_data.get('quality', DownloadQuality.fast),
                            'model_name': request.model_name if request and request.model_name else original_request_data.get('model_name', 'gpt-4o-mini'),
                            'provider_id': request.provider_id if request and request.provider_id else original_request_data.get('provider_id', 'openai'),
                            'screenshot': original_request_data.get('screenshot', False),
                            'link': original_request_data.get('link', False),
                            'format': request.format if request and request.format else original_request_data.get('format', []),
                            'style': request.style if request and request.style else original_request_data.get('style', '简洁'),
                            'extras': original_request_data.get('extras', None),
                            'video_understanding': request.video_understanding if request and request.video_understanding is not None else original_request_data.get('video_understanding', False),
                            'video_interval': request.video_interval if request and request.video_interval is not None else original_request_data.get('video_interval', 0),
                            'grid_size': original_request_data.get('grid_size', []),
                            'title': title
                        }
                        
                        # 使用原task_id重新创建任务
                        new_task_id = task_queue.add_task(
                            task_type=TaskType.SINGLE_VIDEO, 
                            data=task_data,
                            task_id=task_id  # 使用原有的task_id
                        )
                        
                        logger.info(f"✅ 从持久化原始请求数据重建任务成功: {task_id}, 标题: {title}")
                        return R.success({
                            "message": f"任务已从持久化数据重建并重新提交，标题: {title}",
                            "task_id": task_id,
                            "video_url": video_url,
                            "title": title
                        })
                    except Exception as task_error:
                        logger.error(f"❌ 从持久化数据创建任务失败: {task_id}, {task_error}")
                        logger.warning(f"⚠️ 持久化数据创建任务失败，继续尝试其他方法: {task_id}")
                else:
                    logger.warning(f"⚠️ 持久化数据中缺少必要的video_url或platform: {task_id}")
            else:
                logger.info(f"📋 未找到持久化的原始请求数据: {task_id}")
                
        except Exception as e:
            logger.error(f"❌ 从持久化数据重建任务失败: {task_id}, {e}")
        
        # 任务不在队列中，且没有持久化数据，尝试从文件系统重建任务
        logger.info(f"🔍 尝试从文件系统重建任务: {task_id}")
        
        # 检查结果文件是否存在（包含原始任务数据）
        result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")
        audio_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_audio.json")
        
        # 首先尝试从音频metadata文件获取信息（分离文件模式）
        if os.path.exists(audio_path):
            try:
                with open(audio_path, "r", encoding="utf-8") as f:
                    audio_data = json.load(f)
                
                # 从音频文件提取原始任务数据
                video_url = audio_data.get("file_path", "")
                platform = audio_data.get("platform", "")
                title = audio_data.get("title", "未知标题")
                
                if video_url and platform:
                    try:
                        # 重建任务数据（使用默认配置）
                        from app.enmus.note_enums import DownloadQuality
                        
                        task_data = {
                            'video_url': video_url,
                            'platform': platform,
                            'quality': DownloadQuality.fast,
                            'model_name': request.model_name if request and request.model_name else 'gpt-4o-mini',
                            'provider_id': request.provider_id if request and request.provider_id else 'openai',
                            'screenshot': False,
                            'link': False,
                            'format': request.format if request and request.format else [],
                            'style': request.style if request and request.style else '简洁',
                            'extras': None,
                            'video_understanding': request.video_understanding if request and request.video_understanding is not None else False,
                            'video_interval': request.video_interval if request and request.video_interval is not None else 0,
                            'grid_size': [],
                            'title': title
                        }
                        
                        # 使用原task_id重新创建任务
                        new_task_id = task_queue.add_task(
                            task_type=TaskType.SINGLE_VIDEO, 
                            data=task_data,
                            task_id=task_id  # 使用原有的task_id
                        )
                        
                        logger.info(f"✅ 从音频metadata文件重建任务成功: {task_id}")
                        return R.success({
                            "message": f"任务已从音频文件重建并重新提交，标题: {title}",
                            "task_id": task_id
                        })
                    except Exception as task_error:
                        logger.error(f"❌ 从音频文件创建任务失败: {task_id}, {task_error}")
                        logger.warning(f"⚠️ 音频文件创建任务失败，继续尝试其他方法: {task_id}")
                    
            except Exception as e:
                logger.error(f"❌ 读取音频metadata文件失败: {task_id}, {e}")
                # 第一种失败：读取音频metadata文件失败，调用删除老记录重新队列执行
                logger.info(f"🔄 读取音频metadata文件失败，尝试清空重置任务: {task_id}")
                success = clear_and_reset_task(task_id)
                if success:
                    return R.success({
                        "message": "音频文件读取失败，已清空重置并重新提交任务",
                        "task_id": task_id
                    })
                else:
                    return R.error("音频文件读取失败，清空重置任务也失败")
        
        # 如果音频文件不存在或失败，尝试从主结果文件读取
        if os.path.exists(result_path):
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    result_data = json.load(f)
                
                # 检查是否为错误文件
                if "error" in result_data:
                    logger.warning(f"⚠️ 发现错误文件，尝试清空重置任务: {task_id}")
                    success = clear_and_reset_task(task_id, result_data)
                    if success:
                        return R.success({
                            "message": "发现错误文件，已清空重置并重新提交任务",
                            "task_id": task_id
                        })
                    else:
                        return R.error("发现错误文件，清空重置任务失败")
                
                # 从结果文件中提取原始任务数据
                if "audioMeta" in result_data and "transcript" in result_data:
                    # 这是一个完整的结果文件，包含原始数据
                    audio_meta = result_data.get("audioMeta", {})
                    video_url = audio_meta.get("file_path", "")
                    platform = audio_meta.get("platform", "")
                    title = audio_meta.get("title", "未知标题")
                    
                    if video_url and platform:
                        try:
                            # 重建任务数据（使用默认配置）
                            from app.enmus.note_enums import DownloadQuality
                            
                            task_data = {
                                'video_url': video_url,
                                'platform': platform,
                                'quality': DownloadQuality.fast,
                                'model_name': request.model_name if request and request.model_name else 'gpt-4o-mini',
                                'provider_id': request.provider_id if request and request.provider_id else 'openai',
                                'screenshot': False,
                                'link': False,
                                'format': request.format if request and request.format else [],
                                'style': request.style if request and request.style else '简洁',
                                'extras': None,
                                'video_understanding': request.video_understanding if request and request.video_understanding is not None else False,
                                'video_interval': request.video_interval if request and request.video_interval is not None else 0,
                                'grid_size': [],
                                'title': title
                            }
                            
                            # 使用原task_id重新创建任务
                            new_task_id = task_queue.add_task(
                                task_type=TaskType.SINGLE_VIDEO, 
                                data=task_data,
                                task_id=task_id  # 使用原有的task_id
                            )
                            
                            logger.info(f"✅ 从结果文件重建任务成功: {task_id}")
                            return R.success({
                                "message": f"任务已从结果文件重建并重新提交，标题: {title}",
                                "task_id": task_id
                            })
                        except Exception as task_error:
                            logger.error(f"❌ 从结果文件创建任务失败: {task_id}, {task_error}")
                            logger.warning(f"⚠️ 结果文件创建任务失败，尝试清空重置: {task_id}")
                            # 创建任务失败，尝试清空重置
                            success = clear_and_reset_task(task_id, result_data)
                            if success:
                                return R.success({
                                    "message": "结果文件创建任务失败，已清空重置并重新提交任务",
                                    "task_id": task_id
                                })
                            else:
                                return R.error("结果文件创建任务失败，清空重置任务也失败")
                    else:
                        logger.warning(f"⚠️ 结果文件中缺少必要的视频信息: {task_id}")
                        # 结果文件中缺少必要信息，也调用清空重置
                        logger.info(f"🔄 结果文件缺少视频信息，尝试清空重置任务: {task_id}")
                        success = clear_and_reset_task(task_id, result_data)
                        if success:
                            return R.success({
                                "message": "结果文件缺少必要信息，已清空重置并重新提交任务",
                                "task_id": task_id
                            })
                        else:
                            return R.error("结果文件缺少必要信息，清空重置任务失败")
                else:
                    logger.warning(f"⚠️ 结果文件格式不正确: {task_id}")
                    # 第二种失败：结果文件格式不正确，调用删除老记录重新队列执行
                    logger.info(f"🔄 结果文件格式不正确，尝试清空重置任务: {task_id}")
                    success = clear_and_reset_task(task_id, result_data)
                    if success:
                        return R.success({
                            "message": "结果文件格式不正确，已清空重置并重新提交任务",
                            "task_id": task_id
                        })
                    else:
                        return R.error("结果文件格式不正确，清空重置任务失败")
                    
            except Exception as e:
                logger.error(f"❌ 读取结果文件失败: {task_id}, {e}")
                # 读取结果文件失败，也调用清空重置
                logger.info(f"🔄 读取结果文件失败，尝试清空重置任务: {task_id}")
                success = clear_and_reset_task(task_id)
                if success:
                    return R.success({
                        "message": "结果文件读取失败，已清空重置并重新提交任务",
                        "task_id": task_id
                    })
                else:
                    return R.error(f"结果文件读取失败，清空重置任务也失败: {str(e)}")
        else:
            logger.warning(f"⚠️ 未找到任务相关文件: {task_id}")
            # 第三种失败：未找到任务相关文件，调用删除老记录重新队列执行
            logger.info(f"🔄 未找到任务相关文件，尝试清空重置任务: {task_id}")
            success = clear_and_reset_task(task_id)
            if success:
                return R.success({
                    "message": "未找到任务相关文件，已尝试清空重置任务",
                    "task_id": task_id
                })
            else:
                return R.error("未找到任务相关文件，无法重建任务")
        
    except Exception as e:
        logger.error(f"❌ 强制重试任务失败: {e}")
        return R.error(f"强制重试任务失败: {str(e)}")

@router.post("/force_restart_task/{task_id}")
def force_restart_task(task_id: str):
    """强制清理并重新开始任务 - 完全从头开始，清理所有相关文件"""
    try:
        from app.core.task_queue import TaskStatus as QueueTaskStatus, TaskType
        import glob
        
        logger.info(f"🔥 开始强制重新开始任务: {task_id}")
        
        # 1. 首先尝试从持久化的原始请求数据获取任务数据
        request_file_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.request.json")
        task_data = None
        
        if os.path.exists(request_file_path):
            try:
                with open(request_file_path, "r", encoding="utf-8") as f:
                    request_data = json.load(f)
                
                original_request = request_data.get("original_request", {})
                if original_request and original_request.get("video_url"):
                    try:
                        video_url = original_request.get("video_url")
                        platform = original_request.get("platform", "bilibili")
                        title = original_request.get("title", "未知标题")
                        
                        from app.enmus.note_enums import DownloadQuality
                        
                        task_data = {
                            'video_url': video_url,
                            'platform': platform,
                            'quality': original_request.get('quality', DownloadQuality.fast),
                            'model_name': original_request.get('model_name', 'gpt-4o-mini'),
                            'provider_id': original_request.get('provider_id', 'openai'),
                            'screenshot': original_request.get('screenshot', False),
                            'link': original_request.get('link', False),
                            'format': original_request.get('format', []),
                            'style': original_request.get('style', '简洁'),
                            'extras': original_request.get('extras', None),
                            'video_understanding': original_request.get('video_understanding', False),
                            'video_interval': original_request.get('video_interval', 0),
                            'grid_size': original_request.get('grid_size', []),
                            'title': title
                        }
                        
                        logger.info(f"✅ 从持久化请求数据获取任务数据成功: {title} ({video_url})")
                    except Exception as data_error:
                        logger.error(f"❌ 从持久化数据构建任务数据失败: {task_id}, {data_error}")
                        # 如果构建任务数据失败，task_data保持为None
                    
            except Exception as e:
                logger.error(f"❌ 读取持久化请求数据失败: {task_id}, {e}")
        
        # 2. 如果持久化数据不存在，尝试从音频文件获取原始任务数据
        if not task_data:
            audio_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_audio.json")
            
            if os.path.exists(audio_path):
                try:
                    with open(audio_path, "r", encoding="utf-8") as f:
                        audio_data = json.load(f)
                
                    # 从音频文件提取原始任务数据
                    video_url = audio_data.get("file_path", "")
                    # 如果是BV号，转换为B站URL
                    if "BV" in video_url:
                        video_id = os.path.basename(video_url).replace(".mp3", "")
                        video_url = f"https://www.bilibili.com/video/{video_id}"
                    elif not video_url.startswith("http"):
                        # 如果是本地文件路径，尝试从video_id构建URL
                        video_id = audio_data.get("video_id", "")
                        if video_id and video_id.startswith("BV"):
                            video_url = f"https://www.bilibili.com/video/{video_id}"
                        else:
                            video_url = audio_data.get("file_path", "")
                    
                    platform = audio_data.get("platform", "bilibili")
                    title = audio_data.get("title", "未知标题")
                    
                    if video_url and platform:
                        try:
                            # 重建任务数据（使用默认配置，可以后续调整）
                            from app.enmus.note_enums import DownloadQuality
                            
                            task_data = {
                                'video_url': video_url,
                                'platform': platform,
                                'quality': DownloadQuality.fast,
                                'model_name': 'gpt-4o-mini',  # 默认模型
                                'provider_id': 'openai',      # 默认提供者
                                'screenshot': False,
                                'link': False,
                                'format': [],
                                'style': '简洁',
                                'extras': None,
                                'video_understanding': False,
                                'video_interval': 0,
                                'grid_size': [],
                                'title': title
                            }
                            
                            logger.info(f"✅ 从音频文件获取任务数据成功: {title} ({video_url})")
                        except Exception as data_error:
                            logger.error(f"❌ 构建任务数据失败: {task_id}, {data_error}")
                            # 如果构建任务数据失败，task_data保持为None
                except Exception as e:
                    logger.error(f"❌ 读取音频文件失败: {task_id}, {e}")
        
        # 如果没有获取到任务数据，返回错误
        if not task_data:
            logger.error(f"❌ 无法获取任务数据，无法重新开始: {task_id}")
            return R.error("无法获取原始任务数据，请确保任务文件存在")
        
        # 2. 清理所有相关文件
        logger.info(f"🧹 开始清理任务相关文件: {task_id}")
        
        # 清理模式列表
        cleanup_patterns = [
            f"{task_id}.json",
            f"{task_id}.status.json", 
            f"{task_id}.request.json",  # 原始请求数据文件
            f"{task_id}_*.json",
            f"{task_id}_*.md",
            f"{task_id}_*.txt"
        ]
        
        cleaned_files = []
        for pattern in cleanup_patterns:
            file_pattern = os.path.join(NOTE_OUTPUT_DIR, pattern)
            matching_files = glob.glob(file_pattern)
            for file_path in matching_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        cleaned_files.append(os.path.basename(file_path))
                        logger.info(f"🗑️ 已删除文件: {os.path.basename(file_path)}")
                except Exception as e:
                    logger.warning(f"⚠️ 删除文件失败: {os.path.basename(file_path)}, {e}")
        
        # 3. 从任务队列中移除旧任务（如果存在）
        with task_queue._lock:
            if task_id in task_queue.tasks:
                del task_queue.tasks[task_id]
                logger.info(f"🗑️ 已从任务队列移除旧任务: {task_id}")
        
        # 4. 创建全新的任务
        try:
            new_task_id = task_queue.add_task(
                task_type=TaskType.SINGLE_VIDEO, 
                data=task_data,
                task_id=task_id  # 使用原有的task_id
            )
            
            logger.info(f"✅ 强制重新开始任务成功: {task_id}")
            logger.info(f"📋 任务详情: {task_data.get('title', '未知标题')}")
            logger.info(f"🧹 清理了 {len(cleaned_files)} 个文件: {', '.join(cleaned_files)}")
            
            return R.success({
                "message": f"任务已强制重新开始，标题: {task_data.get('title', '未知标题')}",
                "task_id": task_id,
                "video_url": task_data.get('video_url', ''),
                "title": task_data.get('title', '未知标题'),
                "cleaned_files": cleaned_files,
                "restart_time": time.time()
            })
        except Exception as task_error:
            logger.error(f"❌ 强制重新开始任务时创建任务失败: {task_id}, {task_error}")
            return R.error(f"强制重新开始任务失败: 文件已清理但任务创建失败 - {str(task_error)}")
        
    except Exception as e:
        logger.error(f"❌ 强制重新开始任务失败: {task_id}, {e}")
        return R.error(f"强制重新开始任务失败: {str(e)}")

@router.post("/clear_reset_task/{task_id}")
def clear_reset_task(task_id: str):
    """清空并重置单个任务（删除所有相关文件并重新创建）"""
    try:
        logger.info(f"🧹 手动清空重置任务: {task_id}")
        
        # 首先从队列中移除任务（如果存在）
        with task_queue._lock:
            if task_id in task_queue.tasks:
                del task_queue.tasks[task_id]
                logger.info(f"🗑️ 已从队列中移除任务: {task_id}")
        
        # 执行清空重置
        success = clear_and_reset_task(task_id)
        
        if success:
            logger.info(f"✅ 任务清空重置成功: {task_id}")
            return R.success({
                "message": "任务已清空重置，重新进入队列",
                "task_id": task_id
            })
        else:
            logger.warning(f"⚠️ 任务清空重置部分失败: {task_id}")
            return R.success({
                "message": "任务文件已清空，但无法重新创建（缺少原始URL）",
                "task_id": task_id
            })
        
    except Exception as e:
        logger.error(f"❌ 清空重置任务出错: {task_id}, {e}")
        return R.error(f"清空重置任务失败: {str(e)}")

class BatchClearResetRequest(BaseModel):
    """批量清空重置请求模型"""
    task_ids: List[str]
    force_clear: Optional[bool] = False  # 是否强制清空（即使无法重新创建）

@router.post("/batch_clear_reset_tasks")
def batch_clear_reset_tasks(request: BatchClearResetRequest):
    """批量清空重置任务"""
    try:
        task_ids = request.task_ids
        force_clear = request.force_clear
        
        logger.info(f"🧹 批量清空重置任务: {len(task_ids)} 个任务")
        
        results = []
        success_count = 0
        
        for task_id in task_ids:
            try:
                # 从队列中移除任务
                with task_queue._lock:
                    if task_id in task_queue.tasks:
                        del task_queue.tasks[task_id]
                
                # 执行清空重置
                success = clear_and_reset_task(task_id)
                
                if success:
                    results.append({
                        "task_id": task_id,
                        "status": "success",
                        "message": "清空重置成功"
                    })
                    success_count += 1
                else:
                    if force_clear:
                        # 强制清空模式：即使无法重新创建也清空文件
                        results.append({
                            "task_id": task_id,
                            "status": "partial",
                            "message": "文件已清空，但无法重新创建"
                        })
                        success_count += 1
                    else:
                        results.append({
                            "task_id": task_id,
                            "status": "failed",
                            "message": "清空重置失败"
                        })
                
            except Exception as e:
                results.append({
                    "task_id": task_id,
                    "status": "error",
                    "message": f"处理出错: {str(e)}"
                })
        
        logger.info(f"✅ 批量清空重置完成: 成功={success_count}, 总数={len(task_ids)}")
        
        return R.success({
            "results": results,
            "success_count": success_count,
            "total_count": len(task_ids),
            "message": f"批量清空重置完成，成功处理 {success_count}/{len(task_ids)} 个任务"
        })
        
    except Exception as e:
        logger.error(f"❌ 批量清空重置任务出错: {e}")
        return R.error(f"批量清空重置任务失败: {str(e)}")

@router.get("/baidu_pan/file_list")
def get_baidu_pan_file_list(path: str = "/", share_code: str = None, extract_code: str = None):
    """获取百度网盘文件列表 - 使用BaiduPCS-Py"""
    try:
        from app.downloaders.baidupcs_downloader import BaiduPCSDownloader
        
        logger.info(f"🗂️ 获取百度网盘文件列表: path={path}, share_code={share_code}")
        
        downloader = BaiduPCSDownloader()
        
        # 检查认证状态
        if not downloader.is_authenticated():
            return R.error("百度网盘未认证，请先添加用户", code=401)
        
        # 获取文件列表
        try:
            file_list = downloader.get_file_list(path=path, share_code=share_code, extract_code=extract_code)
        except Exception as download_error:
            logger.error(f"❌ 获取百度网盘文件列表失败: {download_error}")
            return R.error(f"获取文件列表失败: {str(download_error)}", code=500)
        
        if not file_list:
            logger.warning("⚠️ 未找到任何文件")
            return R.success({
                "files": [],
                "total": 0,
                "media_count": 0,
                "message": "当前目录为空"
            })
        
        # 计算媒体文件数量
        media_count = sum(1 for f in file_list if f.get("is_media", False))
        
        logger.info(f"✅ 获取文件列表成功: 总计 {len(file_list)} 个项目，其中 {media_count} 个媒体文件")
        
        return R.success({
            "files": file_list,
            "total": len(file_list),
            "media_count": media_count,
            "current_path": path
        })
        
    except Exception as e:
        logger.error(f"❌ 获取百度网盘文件列表失败: {e}")
        return R.error(f"获取文件列表失败: {str(e)}")


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    
    return f"{size_bytes:.1f} PB"


@router.post("/baidu_pan/select_files")
def select_baidu_pan_files(request: dict):
    """选择百度网盘文件并创建下载任务"""
    try:
        selected_files = request.get("selected_files", [])
        task_config = request.get("task_config", {})
        
        if not selected_files:
            return R.error("请选择至少一个文件")
        
        logger.info(f"📁 选择百度网盘文件: {len(selected_files)} 个文件")
        
        created_tasks = []
        
        # 为每个选择的文件创建任务
        for file_info in selected_files:
            try:
                fs_id = file_info.get("fs_id")
                filename = file_info.get("filename")
                file_path = file_info.get("path", "/")
                
                if not fs_id or not filename:
                    logger.warning(f"⚠️ 文件信息不完整，跳过: {file_info}")
                    continue
                
                # 构造百度网盘文件URL
                file_url = f"baidu_pan://file/{fs_id}?filename={filename}&path={file_path}"
                
                # 准备任务数据
                task_data = {
                    'video_url': file_url,
                    'platform': 'baidu_pan',
                    'quality': task_config.get('quality', 'fast'),
                    'model_name': task_config.get('model_name', 'gpt-4o-mini'),
                    'provider_id': task_config.get('provider_id', 'openai'),
                    'screenshot': task_config.get('screenshot', False),
                    'link': task_config.get('link', False),
                    'format': task_config.get('format', []),
                    'style': task_config.get('style', '简洁'),
                    'extras': task_config.get('extras', None),
                    'video_understanding': task_config.get('video_understanding', False),
                    'video_interval': task_config.get('video_interval', 0),
                    'grid_size': task_config.get('grid_size', []),
                    'title': os.path.splitext(filename)[0]  # 去掉扩展名作为标题
                }
                
                # 添加任务到队列
                task_id = task_queue.add_task(TaskType.SINGLE_VIDEO, task_data)
                
                # 保存原始请求数据
                original_request_data = {
                    "video_url": file_url,
                    "platform": "baidu_pan",
                    "title": task_data['title'],
                    **task_config
                }
                save_original_request_data(task_id, original_request_data)
                
                created_tasks.append({
                    "task_id": task_id,
                    "filename": filename,
                    "title": task_data['title']
                })
                
                logger.info(f"✅ 已创建任务: {task_id} - {filename}")
                
            except Exception as task_error:
                logger.error(f"❌ 创建任务失败: {filename}, {task_error}")
                continue
        
        if not created_tasks:
            return R.error("没有成功创建任何任务")
        
        logger.info(f"✅ 百度网盘文件选择完成，共创建 {len(created_tasks)} 个任务")
        
        return R.success({
            "created_tasks": created_tasks,
            "total_tasks": len(created_tasks),
            "message": f"已成功为 {len(created_tasks)} 个文件创建笔记生成任务"
        })
        
    except Exception as e:
        logger.error(f"❌ 选择百度网盘文件失败: {e}")
        return R.error(f"选择文件失败: {str(e)}")


@router.get("/baidu_pan/auth_status")
def get_baidu_pan_auth_status():
    """检查百度网盘认证状态 - 使用BaiduPCS-Py"""
    try:
        from app.downloaders.baidupcs_downloader import BaiduPCSDownloader
        
        downloader = BaiduPCSDownloader()
        is_authenticated = downloader.is_authenticated()
        
        if is_authenticated:
            user_info = downloader.get_current_user_info()
            return R.success({
                "authenticated": True,
                "message": "百度网盘已认证",
                "user_info": user_info,
                "validation_success": True
            })
        else:
            return R.success({
                "authenticated": False,
                "message": "未认证，请使用BaiduPCS-Py添加用户",
                "validation_success": False,
                "setup_guide": {
                    "steps": [
                        "1. 在浏览器中访问 https://pan.baidu.com",
                        "2. 登录您的百度账号", 
                        "3. 按F12打开开发者工具",
                        "4. 转到 Application/应用 -> Storage/存储 -> Cookies",
                        "5. 选择 https://pan.baidu.com",
                        "6. 复制所有cookie值（特别是BDUSS）",
                        "7. 调用 /api/baidupcs/add_user 接口添加用户"
                    ],
                    "required_cookies": ["BDUSS"],
                    "tips": [
                        "确保复制完整的cookie字符串",
                        "cookie中必须包含BDUSS字段",
                        "使用新的BaiduPCS-Py接口进行认证管理"
                    ]
                }
            })
            
    except Exception as e:
        logger.error(f"❌ 检查百度网盘认证状态失败: {e}")
        return R.error(f"检查认证状态失败: {str(e)}")

# @router.post("/baidu_pan/validate_cookie")
# 注意：此路由已废弃，请使用新的BaiduPCS-Py接口
# 新接口: GET /api/baidupcs/auth_status
def validate_baidu_pan_cookie(request: dict):
    """验证百度网盘cookie有效性 - 已废弃"""
    try:
        cookie_string = request.get("cookie", "").strip()
        
        if not cookie_string:
            return R.error("请提供cookie字符串")
        
        # 解析cookie
        critical_cookies = ['BDUSS', 'STOKEN', 'PSTM']
        parsed_cookies = {}
        
        for cookie_pair in cookie_string.split(';'):
            if '=' in cookie_pair:
                name, value = cookie_pair.split('=', 1)
                name = name.strip()
                value = value.strip()
                if name and value:
                    parsed_cookies[name] = value
        
        # 检查关键cookie
        missing_critical = [c for c in critical_cookies if c not in parsed_cookies]
        existing_critical = [c for c in critical_cookies if c in parsed_cookies]
        
        if missing_critical:
            return R.error(
                f"cookie缺少关键字段: {', '.join(missing_critical)}",
                code=400,
                data={
                    "missing_cookies": missing_critical,
                    "existing_cookies": existing_critical,
                    "is_valid": False
                }
            )
        
        # 尝试使用cookie进行API调用验证
        try:
            from app.downloaders.baidupcs_downloader import BaiduPanDownloader
            
            # 临时创建下载器实例进行测试
            downloader = BaiduPanDownloader()
            
            # 临时设置cookie进行验证
            temp_session = downloader.session
            temp_session.cookies.clear()
            
            for name, value in parsed_cookies.items():
                temp_session.cookies.set(name, value, domain='.baidu.com')
            
            # 尝试验证cookie
            if downloader._validate_cookie_status():
                return R.success({
                    "is_valid": True,
                    "message": "cookie验证成功",
                    "existing_cookies": existing_critical,
                    "total_cookies": len(parsed_cookies)
                })
            else:
                return R.error(
                    "cookie验证失败，可能已过期或无效",
                    code=401,
                    data={
                        "is_valid": False,
                        "existing_cookies": existing_critical
                    }
                )
                
        except Exception as validation_error:
            logger.warning(f"⚠️ Cookie验证异常: {validation_error}")
            return R.error(
                f"cookie验证过程中出现错误: {str(validation_error)}",
                code=500,
                data={
                    "is_valid": False,
                    "validation_error": str(validation_error)
                }
            )
        
    except Exception as e:
        logger.error(f"❌ 验证百度网盘cookie失败: {e}")
        return R.error(f"验证cookie失败: {str(e)}")

# @router.get("/baidu_pan/cookie_guide")  
# 注意：此路由已废弃，请使用新的BaiduPCS-Py接口
# 新接口: GET /api/baidupcs/usage_guide
def get_baidu_pan_cookie_guide():
    """获取百度网盘cookie获取指南"""
    try:
        guide = {
            "title": "百度网盘Cookie获取指南",
            "description": "详细的百度网盘cookie获取步骤，确保能正常访问个人网盘文件",
            "steps": [
                {
                    "step": 1,
                    "title": "打开百度网盘",
                    "description": "在浏览器中访问 https://pan.baidu.com",
                    "tips": ["建议使用Chrome、Firefox或Edge浏览器"]
                },
                {
                    "step": 2,
                    "title": "登录账号",
                    "description": "使用您的百度账号登录",
                    "tips": ["确保登录成功，能看到网盘首页"]
                },
                {
                    "step": 3,
                    "title": "打开开发者工具",
                    "description": "按F12键或右键点击\"检查\"打开开发者工具",
                    "tips": ["在Windows/Linux上按F12，在Mac上按Cmd+Option+I"]
                },
                {
                    "step": 4,
                    "title": "找到Cookie",
                    "description": "点击\"Application\"（应用）或\"Storage\"（存储）选项卡",
                    "tips": ["如果找不到，可能叫做\"应用程序\"或\"存储\""]
                },
                {
                    "step": 5,
                    "title": "选择网站Cookie",
                    "description": "在左侧菜单中展开\"Cookies\"，点击\"https://pan.baidu.com\"",
                    "tips": ["确保选择的是pan.baidu.com域名下的cookie"]
                },
                {
                    "step": 6,
                    "title": "复制关键Cookie",
                    "description": "找到并复制BDUSS、STOKEN、PSTM等关键cookie",
                    "tips": [
                        "BDUSS：用户身份凭证，最重要",
                        "STOKEN：会话令牌，必需",
                        "PSTM：时间戳，必需",
                        "建议复制所有可见的cookie以确保完整性"
                    ]
                },
                {
                    "step": 7,
                    "title": "格式化Cookie",
                    "description": "将cookie格式化为: 名称1=值1; 名称2=值2; ...",
                    "tips": [
                        "每个cookie之间用分号和空格分隔",
                        "示例：BDUSS=abc123; STOKEN=def456; PSTM=1234567890"
                    ]
                },
                {
                    "step": 8,
                    "title": "配置到系统",
                    "description": "在系统设置中粘贴完整的cookie字符串",
                    "tips": ["粘贴后系统会自动验证cookie有效性"]
                }
            ],
            "required_cookies": [
                {
                    "name": "BDUSS",
                    "description": "百度用户身份凭证，最重要的认证cookie",
                    "required": True
                },
                {
                    "name": "STOKEN",
                    "description": "百度网盘会话令牌",
                    "required": True
                },
                {
                    "name": "PSTM",
                    "description": "时间戳相关参数",
                    "required": True
                },
                {
                    "name": "BAIDUID",
                    "description": "百度用户ID",
                    "required": False
                }
            ],
            "common_issues": [
                {
                    "issue": "复制的cookie验证失败",
                    "solutions": [
                        "确保已成功登录百度网盘",
                        "检查cookie是否包含BDUSS、STOKEN、PSTM",
                        "刷新页面后重新复制cookie",
                        "清除浏览器缓存后重新登录"
                    ]
                },
                {
                    "issue": "找不到开发者工具",
                    "solutions": [
                        "尝试按F12键",
                        "右键点击页面选择\"检查\"或\"审查元素\"",
                        "在浏览器菜单中查找\"开发者工具\"选项"
                    ]
                },
                {
                    "issue": "Cookie经常过期",
                    "solutions": [
                        "保持浏览器中百度网盘的登录状态",
                        "避免在其他地方重复登录同一账号",
                        "定期更新cookie（建议每周更新一次）"
                    ]
                }
            ],
            "security_notes": [
                "Cookie包含您的登录凭证，请妥善保管",
                "不要将cookie分享给他人",
                "如发现cookie泄露，请及时修改密码",
                "建议定期更新cookie以确保安全"
            ]
        }
        
        return R.success(guide)
        
    except Exception as e:
        logger.error(f"❌ 获取cookie指南失败: {e}")
        return R.error(f"获取cookie指南失败: {str(e)}")

# @router.post("/baidu_pan/save_cookie")
# 注意：此路由已废弃，请使用新的BaiduPCS-Py接口  
# 新接口: POST /api/baidupcs/add_user
def save_baidu_pan_cookie(request: dict):
    """保存百度网盘cookie - 已废弃"""
    try:
        cookie_string = request.get("cookie", "").strip()
        
        if not cookie_string:
            return R.error("请提供cookie字符串")
        
        logger.info(f"💾 准备保存百度网盘cookie")
        
        # 先验证cookie有效性
        try:
            # 解析并验证cookie
            critical_cookies = ['BDUSS', 'STOKEN', 'PSTM']
            parsed_cookies = {}
            
            for cookie_pair in cookie_string.split(';'):
                if '=' in cookie_pair:
                    name, value = cookie_pair.split('=', 1)
                    name = name.strip()
                    value = value.strip()
                    if name and value:
                        parsed_cookies[name] = value
            
            # 检查关键cookie
            missing_critical = [c for c in critical_cookies if c not in parsed_cookies]
            if missing_critical:
                return R.error(
                    f"cookie缺少关键字段: {', '.join(missing_critical)}",
                    code=400,
                    data={
                        "missing_cookies": missing_critical,
                        "saved": False
                    }
                )
            
            # 尝试验证cookie有效性
            from app.downloaders.baidupcs_downloader import BaiduPanDownloader
            
            # 临时测试cookie
            test_downloader = BaiduPanDownloader()
            test_session = test_downloader.session
            test_session.cookies.clear()
            
            for name, value in parsed_cookies.items():
                test_session.cookies.set(name, value, domain='.baidu.com')
            
            # 验证cookie
            if not test_downloader._validate_cookie_status():
                logger.warning("⚠️ Cookie验证失败，但将继续保存")
            
        except Exception as validation_error:
            logger.warning(f"⚠️ Cookie验证异常: {validation_error}")
            # 验证失败但仍然允许保存
        
        # 保存cookie
        try:
            from app.services.cookie_manager import CookieConfigManager
            cookie_manager = CookieConfigManager()
            
            cookie_manager.set("baidu_pan", cookie_string)
            
            # 验证保存是否成功
            saved_cookie = cookie_manager.get("baidu_pan")
            if saved_cookie and saved_cookie == cookie_string:
                logger.info("✅ 百度网盘cookie保存成功")
                
                return R.success({
                    "message": "百度网盘cookie保存成功",
                    "cookie_length": len(cookie_string),
                    "existing_cookies": list(parsed_cookies.keys()),
                    "saved": True
                })
            else:
                logger.error("❌ Cookie保存验证失败")
                return R.error("Cookie保存失败，请重试")
                
        except Exception as save_error:
            logger.error(f"❌ 保存cookie失败: {save_error}")
            return R.error(f"保存cookie失败: {str(save_error)}")
        
    except Exception as e:
        logger.error(f"❌ 保存百度网盘cookie失败: {e}")
        return R.error(f"保存cookie失败: {str(e)}")

# @router.delete("/baidu_pan/clear_cookie")
# 注意：此路由已废弃，请使用新的BaiduPCS-Py接口
# 新接口: POST /api/baidupcs/remove_user  
def clear_baidu_pan_cookie():
    """清除百度网盘cookie - 已废弃"""
    try:
        from app.services.cookie_manager import CookieConfigManager
        
        cookie_manager = CookieConfigManager()
        
        # 检查是否存在cookie
        existing_cookie = cookie_manager.get("baidu_pan")
        if not existing_cookie:
            return R.success({
                "message": "百度网盘cookie不存在，无需清除",
                "cleared": False
            })
        
        # 删除cookie
        cookie_manager.delete("baidu_pan")
        
        # 验证删除是否成功
        remaining_cookie = cookie_manager.get("baidu_pan")
        if remaining_cookie:
            logger.error("❌ Cookie删除验证失败")
            return R.error("Cookie删除失败")
        
        logger.info("✅ 百度网盘cookie清除成功")
        
        return R.success({
            "message": "百度网盘cookie已清除",
            "cleared": True
        })
        
    except Exception as e:
        logger.error(f"❌ 清除百度网盘cookie失败: {e}")
        return R.error(f"清除cookie失败: {str(e)}")

@router.post("/clear_baidu_pan_cookie")
def clear_baidu_pan_cookie():
    try:
        from app.services.baidupcs_service import clear_cookie
        clear_cookie()
        logger.info("✅ 百度网盘cookie已清除")
        return R.success("Cookie已清除")
    except Exception as e:
        logger.error(f"❌ 清除百度网盘cookie失败: {e}")
        return R.error(f"清除cookie失败: {str(e)}")

@router.post("/debug/force_retry_task/{task_id}")
def debug_force_retry_task(task_id: str):
    """调试用：强制重试单个任务（检查存储路径）"""
    try:
        logger.warning(f"🔍 [DEBUG] 调试强制重试单个任务: {task_id}")
        
        # 检查task_persistence目录
        from app.core.task_queue import task_queue
        task_persistence_dir = task_queue.persistence_dir
        logger.warning(f"  - 任务持久化目录: {task_persistence_dir}")
        task_file = os.path.join(task_persistence_dir, f"{task_id}.json")
        logger.warning(f"  - 任务文件存在?: {os.path.exists(task_file)}")
        
        # 检查note_results目录
        note_results_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "note_results"))
        logger.warning(f"  - 笔记结果目录: {note_results_dir}")
        logger.warning(f"  - 笔记结果目录存在?: {os.path.exists(note_results_dir)}")
        
        request_file = os.path.join(note_results_dir, f"{task_id}.request.json")
        logger.warning(f"  - 请求文件存在?: {os.path.exists(request_file)}")
        
        if os.path.exists(request_file):
            try:
                with open(request_file, 'r', encoding='utf-8') as f:
                    request_data = json.load(f)
                logger.warning(f"  - 请求数据键: {list(request_data.keys())}")
                
                original_request = request_data.get("original_request", {})
                logger.warning(f"  - 原始请求键: {list(original_request.keys())}")
                
                if "video_url" in original_request and "platform" in original_request:
                    logger.warning(f"  - 找到必要的video_url和platform")
                    return R.success({
                        "message": "找到了有效的请求文件",
                        "task_id": task_id,
                        "request_file": request_file,
                        "keys": list(original_request.keys()),
                        "video_url": original_request.get("video_url"),
                        "platform": original_request.get("platform")
                    })
                else:
                    logger.warning(f"  - 原始请求缺少必要信息")
                    return R.error("请求文件中缺少必要的video_url或platform")
            except Exception as e:
                logger.error(f"  - 加载请求文件失败: {e}")
                return R.error(f"加载请求文件失败: {str(e)}")
        else:
            logger.warning(f"  - 请求文件不存在")
            return R.error("请求文件不存在")
    except Exception as e:
        logger.error(f"❌ 调试重试任务失败: {e}")
        return R.error(f"调试失败: {str(e)}")
