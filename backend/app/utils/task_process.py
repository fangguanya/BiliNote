from typing import Any, Dict, Optional
from app.utils.logger import get_logger
from app.enmus.note_enums import DownloadQuality

logger = get_logger(__name__)

def process_single_video_task(task_id: str, task_data: Dict[str, Any]) -> Any:
    """处理单个视频任务"""
    from app.routers.note import run_note_task
    
    logger.info(f"📺 处理单视频: {task_data.get('video_url')}")
    
    # 调用原有的视频处理逻辑
    result = run_note_task(
        task_id=task_id,
        video_url=task_data['video_url'],
        platform=task_data['platform'],
        quality=task_data['quality'],
        link=task_data.get('link', False),
        screenshot=task_data.get('screenshot', False),
        model_name=task_data['model_name'],
        provider_id=task_data['provider_id'],
        _format=task_data.get('format', []),
        style=task_data.get('style'),
        extras=task_data.get('extras'),
        video_understanding=task_data.get('video_understanding', False),
        video_interval=task_data.get('video_interval', 0),
        grid_size=task_data.get('grid_size', [])
    )
    
    return result


def process_collection_task(task_id: str, task_data: Dict[str, Any], add_task_func) -> Any:
    """处理合集任务"""
    from app.utils.url_parser import extract_collection_videos
    from app.core.task_queue import TaskType
    
    logger.info(f"🎬 处理合集: {task_data.get('video_url')}")
    
    # 提取合集视频列表
    videos = extract_collection_videos(
        task_data['video_url'],
        task_data['platform'],
        task_data.get('max_collection_videos', 50)
    )
    
    logger.info(f"📹 合集包含 {len(videos)} 个视频")
    
    # 为每个视频创建单独的任务
    created_tasks = []
    for video_url, title in videos:
        video_task_data = task_data.copy()
        video_task_data['video_url'] = video_url
        video_task_data['title'] = title
        
        video_task_id = add_task_func(TaskType.SINGLE_VIDEO, video_task_data)
        created_tasks.append({
            'task_id': video_task_id,
            'video_url': video_url,
            'title': title
        })
        
    logger.info(f"✅ 合集处理完成，创建了 {len(created_tasks)} 个子任务")
    
    return {
        'total_videos': len(videos),
        'created_tasks': len(created_tasks),
        'task_list': created_tasks
    } 