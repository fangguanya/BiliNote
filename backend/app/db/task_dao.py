import json
import sqlite3
from typing import List, Optional, Dict, Any
from datetime import datetime
from .sqlite_client import get_connection
from app.utils.logger import get_logger
from app.models.task_model import TaskModel, TaskCreate, TaskUpdate, TaskStatus

logger = get_logger(__name__)

def init_tasks_table():
    """初始化任务表"""
    conn = get_connection()
    if conn is None:
        logger.error("Failed to connect to the database.")
        return
    
    cursor = conn.cursor()
    
    # 创建任务表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            platform TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            markdown TEXT, -- JSON格式存储markdown版本数组
            transcript TEXT, -- JSON格式存储transcript对象
            audio_meta TEXT, -- JSON格式存储audioMeta对象
            notion_info TEXT, -- JSON格式存储notion信息
            form_data TEXT NOT NULL -- JSON格式存储formData对象
        )
    """)
    
    # 创建索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_platform ON tasks(platform)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)
    """)
    
    try:
        conn.commit()
        conn.close()
        logger.info("Tasks table created successfully.")
    except Exception as e:
        logger.error(f"Failed to create tasks table: {e}")
        if conn:
            conn.close()

def create_task(task_data: TaskCreate) -> bool:
    """创建新任务"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO tasks (id, status, platform, created_at, updated_at, form_data)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            task_data.id,
            TaskStatus.PENDING.value,
            task_data.platform,
            now,
            now,
            json.dumps(task_data.formData.model_dump())
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"Task created successfully: {task_data.id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create task {task_data.id}: {e}")
        if conn:
            conn.close()
        return False

def get_task_by_id(task_id: str) -> Optional[TaskModel]:
    """根据ID获取任务"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, status, platform, created_at, markdown, transcript, 
                   audio_meta, notion_info, form_data
            FROM tasks WHERE id = ?
        """, (task_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return None
            
        return _row_to_task_model(result)
        
    except Exception as e:
        logger.error(f"Failed to get task {task_id}: {e}")
        if conn:
            conn.close()
        return None

def get_tasks(limit: int = 100, offset: int = 0, status: Optional[str] = None) -> List[TaskModel]:
    """获取任务列表"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT id, status, platform, created_at, markdown, transcript, 
                   audio_meta, notion_info, form_data
            FROM tasks
        """
        params = []
        
        if status:
            query += " WHERE status = ?"
            params.append(status)
            
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        return [_row_to_task_model(row) for row in results]
        
    except Exception as e:
        logger.error(f"Failed to get tasks: {e}")
        if conn:
            conn.close()
        return []

def update_task(task_id: str, update_data: TaskUpdate) -> bool:
    """更新任务"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 构建更新字段
        update_fields = []
        params = []
        
        if update_data.status is not None:
            update_fields.append("status = ?")
            params.append(update_data.status.value)
            
        if update_data.markdown is not None:
            update_fields.append("markdown = ?")
            params.append(json.dumps(_serialize_markdown(update_data.markdown)))
            
        if update_data.transcript is not None:
            update_fields.append("transcript = ?")
            params.append(json.dumps(update_data.transcript.model_dump()))
            
        if update_data.audioMeta is not None:
            update_fields.append("audio_meta = ?")
            params.append(json.dumps(update_data.audioMeta.model_dump()))
            
        if update_data.notion is not None:
            update_fields.append("notion_info = ?")
            params.append(json.dumps(update_data.notion.model_dump()))
        
        if not update_fields:
            return True
            
        update_fields.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(task_id)
        
        query = f"UPDATE tasks SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, params)
        
        conn.commit()
        conn.close()
        logger.info(f"Task updated successfully: {task_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update task {task_id}: {e}")
        if conn:
            conn.close()
        return False

def delete_task(task_id: str) -> bool:
    """删除任务"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"Task deleted successfully: {task_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete task {task_id}: {e}")
        if conn:
            conn.close()
        return False

def get_tasks_count(status: Optional[str] = None) -> int:
    """获取任务总数"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        query = "SELECT COUNT(*) FROM tasks"
        params = []
        
        if status:
            query += " WHERE status = ?"
            params.append(status)
            
        cursor.execute(query, params)
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0
        
    except Exception as e:
        logger.error(f"Failed to get tasks count: {e}")
        if conn:
            conn.close()
        return 0

def _row_to_task_model(row) -> TaskModel:
    """将数据库行转换为TaskModel"""
    from app.models.task_model import TaskModel, AudioMeta, Transcript, NotionInfo, FormData, Markdown
    
    id, status, platform, created_at, markdown, transcript, audio_meta, notion_info, form_data = row
    
    # 解析JSON字段
    markdown_data = ""
    if markdown:
        try:
            markdown_json = json.loads(markdown)
            if isinstance(markdown_json, list):
                markdown_data = [Markdown(**item) for item in markdown_json]
            else:
                markdown_data = markdown_json
        except:
            markdown_data = markdown or ""
    
    transcript_data = Transcript()
    if transcript:
        try:
            transcript_data = Transcript(**json.loads(transcript))
        except:
            pass
    
    audio_meta_data = AudioMeta()
    if audio_meta:
        try:
            audio_meta_data = AudioMeta(**json.loads(audio_meta))
        except:
            pass
    
    notion_data = None
    if notion_info:
        try:
            notion_data = NotionInfo(**json.loads(notion_info))
        except:
            pass
    
    form_data_obj = FormData(video_url="", platform=platform, model_name="", provider_id="")
    if form_data:
        try:
            form_data_obj = FormData(**json.loads(form_data))
        except:
            pass
    
    return TaskModel(
        id=id,
        status=TaskStatus(status),
        platform=platform,
        createdAt=created_at,
        markdown=markdown_data,
        transcript=transcript_data,
        audioMeta=audio_meta_data,
        notion=notion_data,
        formData=form_data_obj
    )

def _serialize_markdown(markdown) -> Any:
    """序列化markdown数据"""
    if isinstance(markdown, str):
        return markdown
    elif isinstance(markdown, list):
        return [item.model_dump() if hasattr(item, 'model_dump') else item for item in markdown]
    else:
        return markdown 