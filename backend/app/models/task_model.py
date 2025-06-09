from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Union
from enum import Enum
from datetime import datetime

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class AudioMeta(BaseModel):
    cover_url: str = ""
    duration: int = 0
    file_path: str = ""
    platform: str = ""
    raw_info: Optional[Any] = None
    title: str = ""
    video_id: str = ""

class Segment(BaseModel):
    start: float
    end: float
    text: str

class Transcript(BaseModel):
    full_text: str = ""
    language: str = ""
    raw: Optional[Any] = None
    segments: List[Segment] = []

class Markdown(BaseModel):
    ver_id: str
    content: str
    style: str = ""
    model_name: str = ""
    created_at: str

class NotionInfo(BaseModel):
    saved: bool = False
    pageId: Optional[str] = None
    pageUrl: Optional[str] = None
    savedAt: Optional[str] = None
    autoSave: bool = False

class FormData(BaseModel):
    video_url: str
    link: Optional[bool] = None
    screenshot: Optional[bool] = None
    platform: str
    quality: str = "high"
    model_name: str
    provider_id: str
    style: Optional[str] = None
    format: Optional[List[str]] = None
    extras: Optional[str] = None
    video_understanding: Optional[bool] = False
    video_interval: Optional[int] = None
    grid_size: Optional[List[int]] = None
    max_collection_videos: Optional[int] = None
    auto_save_notion: Optional[bool] = False

class TaskModel(BaseModel):
    id: str
    markdown: Union[str, List[Markdown]] = ""
    transcript: Transcript = Transcript()
    status: TaskStatus = TaskStatus.PENDING
    audioMeta: AudioMeta = AudioMeta()
    createdAt: str
    platform: str
    notion: Optional[NotionInfo] = None
    formData: FormData

class TaskCreate(BaseModel):
    id: str
    platform: str
    formData: FormData

class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    markdown: Optional[Union[str, List[Markdown]]] = None
    transcript: Optional[Transcript] = None
    audioMeta: Optional[AudioMeta] = None
    notion: Optional[NotionInfo] = None

class TaskResponse(BaseModel):
    tasks: List[TaskModel]
    total: int
    currentTaskId: Optional[str] = None 