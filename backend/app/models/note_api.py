from typing import List, Dict, Any, Optional, Union, Generic, TypeVar
from pydantic import BaseModel

# 定义泛型类型变量
T = TypeVar('T')


class TaskInfo(BaseModel):
    """任务信息"""
    task_id: str
    video_url: str
    title: str


class SingleVideoResponse(BaseModel):
    """单视频响应"""
    is_collection: bool = False
    task_id: str


class CollectionResponse(BaseModel):
    """合集响应"""
    is_collection: bool = True
    total_videos: int
    created_tasks: int
    task_list: List[TaskInfo]
    message: str


class StandardResponse(BaseModel, Generic[T]):
    """标准API响应格式"""
    success: bool
    data: T
    message: str
    code: Optional[int] = 200 