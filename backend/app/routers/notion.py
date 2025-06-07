import json
import os  
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.notion_service import NotionService
from app.models.notes_model import NoteResult
from app.utils.response import ResponseWrapper as R
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

NOTE_OUTPUT_DIR = "note_results"

class NotionTokenRequest(BaseModel):
    """Notion令牌请求模型"""
    token: str

class SaveToNotionRequest(BaseModel):
    """保存到Notion请求模型"""
    task_id: str
    token: str
    database_id: Optional[str] = None
    parent_page_id: Optional[str] = None

@router.post("/test_connection")
def test_notion_connection(request: NotionTokenRequest):
    """测试Notion连接"""
    try:
        notion_service = NotionService(request.token)
        is_connected = notion_service.test_connection()
        
        if is_connected:
            return R.success({
                "connected": True,
                "message": "Notion连接成功"
            })
        else:
            return R.error("Notion连接失败，请检查令牌是否正确")
            
    except Exception as e:
        logger.error(f"测试Notion连接失败: {e}")
        return R.error(f"连接测试失败: {str(e)}")

@router.post("/list_databases")
def list_notion_databases(request: NotionTokenRequest):
    """获取Notion数据库列表"""
    try:
        notion_service = NotionService(request.token)
        databases = notion_service.list_databases()
        
        return R.success({
            "databases": databases,
            "count": len(databases)
        })
        
    except Exception as e:
        logger.error(f"获取数据库列表失败: {e}")
        return R.error(f"获取数据库列表失败: {str(e)}")

@router.post("/save_note")
def save_note_to_notion(request: SaveToNotionRequest):
    """保存笔记到Notion"""
    try:
        # 检查任务结果文件是否存在
        result_path = os.path.join(NOTE_OUTPUT_DIR, f"{request.task_id}.json")
        if not os.path.exists(result_path):
            return R.error("笔记文件未找到，请确保任务已完成")
        
        # 读取笔记数据
        with open(result_path, "r", encoding="utf-8") as f:
            note_data = json.load(f)
        
        # 检查是否有错误
        if "error" in note_data:
            return R.error(f"笔记生成失败: {note_data['error']}")
        
        # 重构NoteResult对象
        # 由于从JSON加载，需要重新构建对象结构
        try:
            # 创建一个简化的note_result对象用于Notion导出
            from app.models.audio_model import AudioDownloadResult
            from app.models.transcriber_model import TranscriptResult, TranscriptSegment
            
            # 重建AudioDownloadResult
            audio_meta_data = note_data.get('audio_meta', {})
            audio_meta = type('AudioMeta', (), {
                'title': audio_meta_data.get('title', '未命名笔记'),
                'duration': audio_meta_data.get('duration'),
                'platform': audio_meta_data.get('platform', ''),
                'video_id': audio_meta_data.get('video_id', ''),
                'url': audio_meta_data.get('url', ''),
                'cover_url': audio_meta_data.get('cover_url', ''),
                'file_path': audio_meta_data.get('file_path', ''),
                'raw_info': audio_meta_data.get('raw_info', {})
            })()
            
            # 重建TranscriptResult（简化版）
            transcript_data = note_data.get('transcript', {})
            transcript = type('Transcript', (), {
                'language': transcript_data.get('language', ''),
                'full_text': transcript_data.get('full_text', ''),
                'segments': transcript_data.get('segments', [])
            })()
            
            # 创建NoteResult对象
            note_result = type('NoteResult', (), {
                'markdown': note_data.get('markdown', ''),
                'transcript': transcript,
                'audio_meta': audio_meta
            })()
            
        except Exception as e:
            logger.error(f"重构笔记数据失败: {e}")
            return R.error(f"笔记数据格式错误: {str(e)}")
        
        # 初始化Notion服务
        notion_service = NotionService(request.token)
        
        # 根据是否提供database_id来决定创建方式
        if request.database_id:
            # 在数据库中创建页面
            result = notion_service.create_page_in_database(request.database_id, note_result)
        else:
            # 创建独立页面
            result = notion_service.create_standalone_page(note_result, request.parent_page_id)
        
        if result["success"]:
            logger.info(f"成功保存笔记到Notion: {result['page_id']}")
            return R.success({
                "page_id": result["page_id"],
                "url": result["url"],
                "title": result["title"],
                "message": "笔记已成功保存到Notion"
            })
        else:
            return R.error(f"保存到Notion失败: {result['error']}")
            
    except Exception as e:
        logger.error(f"保存到Notion失败: {e}")
        return R.error(f"保存失败: {str(e)}")

@router.get("/health")
def notion_health_check():
    """Notion服务健康检查"""
    return R.success({
        "service": "notion",
        "status": "healthy",
        "message": "Notion集成服务运行正常"
    }) 