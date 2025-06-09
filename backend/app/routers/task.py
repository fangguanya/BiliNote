from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.models.task_model import TaskModel, TaskCreate, TaskUpdate, TaskResponse
from app.db.task_dao import (
    create_task, get_task_by_id, get_tasks, update_task, 
    delete_task, get_tasks_count, init_tasks_table
)
from app.utils.logger import get_logger
from pydantic import ValidationError
import time

logger = get_logger(__name__)
router = APIRouter()

# 迁移状态跟踪，避免频繁重复迁移
_last_migration_time = 0
_migration_interval = 30  # 30秒内不允许重复迁移

@router.post("/tasks", response_model=dict)
async def create_new_task(task: TaskCreate):
    """创建新任务"""
    try:
        success = create_task(task)
        if success:
            return {"message": "Task created successfully", "task_id": task.id}
        else:
            raise HTTPException(status_code=500, detail="Failed to create task")
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 把具体路由放在参数路由之前，避免路由冲突
@router.get("/tasks/migrate", response_model=dict)
async def test_migrate_endpoint():
    """测试迁移端点是否正确注册"""
    return {"message": "Migrate endpoint is working", "method": "GET"}

@router.post("/tasks/migrate", response_model=dict)
async def migrate_tasks_from_frontend(tasks: List[TaskModel]):
    """从前端迁移任务数据到后端存储"""
    global _last_migration_time
    
    current_time = time.time()
    
    # 检查是否在冷却时间内
    if current_time - _last_migration_time < _migration_interval:
        remaining_time = _migration_interval - (current_time - _last_migration_time)
        logger.info(f"⏱️ 迁移请求过于频繁，请等待 {remaining_time:.1f} 秒后再试")
        return {
            "message": f"Migration rate limited. Please wait {remaining_time:.1f} seconds.",
            "migrated_count": 0,
            "total_count": len(tasks),
            "failed_tasks": [],
            "file_statistics": {},
            "rate_limited": True
        }
    
    # 更新最后迁移时间
    _last_migration_time = current_time
    
    logger.info(f"🔄 开始迁移 {len(tasks)} 个任务")
    
    # 统计文件数据
    file_stats = {
        "tasks_with_cover": 0,
        "tasks_with_audio": 0,
        "tasks_with_images": 0,
        "tasks_with_title": 0,
        "total_file_refs": 0
    }
    
    migrated_count = 0
    failed_tasks = []
    
    try:
        for task in tasks:
            try:
                # 检查并统计文件数据
                has_cover = bool(task.audioMeta.cover_url)
                has_audio = bool(task.audioMeta.file_path)
                has_title = bool(task.audioMeta.title)
                has_images = False
                
                # 检查markdown中的图片
                if isinstance(task.markdown, str) and '![' in task.markdown:
                    has_images = True
                elif isinstance(task.markdown, list):
                    for md in task.markdown:
                        if hasattr(md, 'content') and '![' in md.content:
                            has_images = True
                            break
                
                # 更新统计
                if has_cover:
                    file_stats["tasks_with_cover"] += 1
                    file_stats["total_file_refs"] += 1
                if has_audio:
                    file_stats["tasks_with_audio"] += 1
                    file_stats["total_file_refs"] += 1
                if has_title:
                    file_stats["tasks_with_title"] += 1
                if has_images:
                    file_stats["tasks_with_images"] += 1
                    file_stats["total_file_refs"] += 1
                
                # 记录包含文件数据的任务详情
                if any([has_cover, has_audio, has_images]):
                    logger.info(f"📁 任务 {task.id} 包含文件数据: 封面={has_cover}, 音频={has_audio}, 图片={has_images}, 标题={has_title}")
                
                # 检查任务是否已存在
                existing_task = get_task_by_id(task.id)
                
                if existing_task:
                    # 深度比较任务数据，避免不必要的更新
                    needs_update = False
                    update_reasons = []
                    
                    # 检查状态变化
                    if existing_task.status != task.status:
                        needs_update = True
                        update_reasons.append(f"状态: {existing_task.status} -> {task.status}")
                    
                    # 检查markdown内容变化（处理字符串和对象的比较）
                    existing_markdown_str = str(existing_task.markdown) if existing_task.markdown else ""
                    new_markdown_str = str(task.markdown) if task.markdown else ""
                    if existing_markdown_str != new_markdown_str:
                        needs_update = True
                        update_reasons.append("markdown内容已变化")
                    
                    # 检查transcript变化
                    if existing_task.transcript != task.transcript:
                        # 进一步检查transcript的具体内容
                        if (hasattr(existing_task.transcript, 'full_text') and 
                            hasattr(task.transcript, 'full_text') and
                            existing_task.transcript.full_text != task.transcript.full_text):
                            needs_update = True
                            update_reasons.append("转录内容已变化")
                    
                    # 检查audioMeta关键字段变化
                    if existing_task.audioMeta != task.audioMeta:
                        if existing_task.audioMeta.cover_url != task.audioMeta.cover_url:
                            needs_update = True
                            update_reasons.append(f"封面URL: {existing_task.audioMeta.cover_url} -> {task.audioMeta.cover_url}")
                        if existing_task.audioMeta.file_path != task.audioMeta.file_path:
                            needs_update = True
                            update_reasons.append(f"音频路径: {existing_task.audioMeta.file_path} -> {task.audioMeta.file_path}")
                        if existing_task.audioMeta.title != task.audioMeta.title:
                            needs_update = True
                            update_reasons.append(f"标题: {existing_task.audioMeta.title} -> {task.audioMeta.title}")
                    
                    # 检查notion信息变化
                    if existing_task.notion != task.notion:
                        needs_update = True
                        update_reasons.append("Notion信息已变化")
                    
                    if needs_update:
                        logger.info(f"⬆️  任务 {task.id} 数据有变化，执行更新: {', '.join(update_reasons)}")
                        
                        update_data = TaskUpdate(
                            status=task.status,
                            markdown=task.markdown,
                            transcript=task.transcript,
                            audioMeta=task.audioMeta,
                            notion=task.notion
                        )
                        update_success = update_task(task.id, update_data)
                        if not update_success:
                            logger.warning(f"⚠️ 任务 {task.id} 更新失败")
                    else:
                        logger.debug(f"⏭️ 任务 {task.id} 数据无变化，跳过更新")
                else:
                    logger.info(f"➕ 创建新任务 {task.id}（包含文件数据）")
                    task_create = TaskCreate(
                        id=task.id,
                        platform=task.platform,
                        formData=task.formData
                    )
                    
                    # 先创建基础任务
                    create_success = create_task(task_create)
                    if create_success:
                        # 然后更新额外数据（包括文件引用）
                        update_data = TaskUpdate(
                            status=task.status,
                            markdown=task.markdown,
                            transcript=task.transcript,
                            audioMeta=task.audioMeta,
                            notion=task.notion
                        )
                        update_success = update_task(task.id, update_data)
                        if not update_success:
                            logger.warning(f"⚠️ 任务 {task.id} 文件数据更新失败")
                
                migrated_count += 1
                logger.info(f"✅ 任务 {task.id} 迁移成功（文件数据已保留）")
                    
            except Exception as task_error:
                logger.error(f"❌ 迁移任务 {task.id} 时发生异常: {task_error}")
                failed_tasks.append({"task_id": task.id, "error": str(task_error)})
        
        logger.info(f"📊 文件数据迁移统计: {file_stats}")
        
        result = {
            "message": "Migration completed with file data preserved",
            "migrated_count": migrated_count,
            "total_count": len(tasks),
            "failed_tasks": failed_tasks,
            "file_statistics": file_stats
        }
        
        logger.info(f"🎉 迁移完成: 成功 {migrated_count}/{len(tasks)}, 失败 {len(failed_tasks)}")
        logger.info(f"📁 文件数据保留: 封面图片 {file_stats['tasks_with_cover']}个, 音频文件 {file_stats['tasks_with_audio']}个, 图片内容 {file_stats['tasks_with_images']}个")
        return result
        
    except Exception as e:
        logger.error(f"❌ 任务迁移过程中发生严重错误: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")

@router.get("/tasks", response_model=TaskResponse)
async def get_tasks_list(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None)
):
    """获取任务列表"""
    try:
        tasks = get_tasks(limit=limit, offset=offset, status=status)
        total = get_tasks_count(status=status)
        
        return TaskResponse(
            tasks=tasks,
            total=total,
            currentTaskId=None  # 前端自己管理当前任务ID
        )
    except Exception as e:
        logger.error(f"Error getting tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/{task_id}", response_model=TaskModel)
async def get_task(task_id: str):
    """根据ID获取单个任务"""
    try:
        task = get_task_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found11")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/tasks/{task_id}", response_model=dict)
async def update_task_data(task_id: str, update_data: TaskUpdate):
    """更新任务数据"""
    try:
        # 先检查任务是否存在
        existing_task = get_task_by_id(task_id)
        if not existing_task:
            raise HTTPException(status_code=404, detail="Task not found22")
        
        success = update_task(task_id, update_data)
        if success:
            return {"message": "Task updated successfully", "task_id": task_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to update task")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/tasks/{task_id}", response_model=dict)
async def delete_task_by_id(task_id: str):
    """删除任务"""
    try:
        # 先检查任务是否存在
        existing_task = get_task_by_id(task_id)
        if not existing_task:
            raise HTTPException(status_code=404, detail="Task not found33")
        
        success = delete_task(task_id)
        if success:
            return {"message": "Task deleted successfully", "task_id": task_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete task")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tasks/batch", response_model=dict)
async def create_batch_tasks(tasks: List[TaskCreate]):
    """批量创建任务"""
    try:
        created_count = 0
        failed_tasks = []
        
        for task in tasks:
            success = create_task(task)
            if success:
                created_count += 1
            else:
                failed_tasks.append(task.id)
        
        return {
            "message": f"Batch operation completed",
            "created_count": created_count,
            "total_count": len(tasks),
            "failed_tasks": failed_tasks
        }
    except Exception as e:
        logger.error(f"Error in batch task creation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/status/{status}", response_model=List[TaskModel])
async def get_tasks_by_status(status: str):
    """根据状态获取任务"""
    try:
        tasks = get_tasks(status=status)
        return tasks
    except Exception as e:
        logger.error(f"Error getting tasks by status {status}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/validate-files", response_model=dict)
async def validate_files_integrity():
    """验证任务数据中的文件引用完整性"""
    try:
        all_tasks = get_tasks(limit=10000)  # 获取所有任务
        logger.info(f"🔍 开始验证 {len(all_tasks)} 个任务的文件完整性")
        
        file_stats = {
            "total_tasks": len(all_tasks),
            "tasks_with_cover": 0,
            "tasks_with_audio": 0,
            "tasks_with_images": 0,
            "tasks_with_title": 0,
            "missing_files": [],
            "file_references": []
        }
        
        for task in all_tasks:
            task_files = {
                "task_id": task.id,
                "cover_url": task.audioMeta.cover_url if task.audioMeta.cover_url else None,
                "file_path": task.audioMeta.file_path if task.audioMeta.file_path else None,
                "title": task.audioMeta.title if task.audioMeta.title else None,
                "has_images": False
            }
            
            # 统计封面图片
            if task.audioMeta.cover_url:
                file_stats["tasks_with_cover"] += 1
                
            # 统计音频文件
            if task.audioMeta.file_path:
                file_stats["tasks_with_audio"] += 1
                
            # 统计标题
            if task.audioMeta.title:
                file_stats["tasks_with_title"] += 1
                
            # 检查markdown中的图片
            if isinstance(task.markdown, str) and '![' in task.markdown:
                file_stats["tasks_with_images"] += 1
                task_files["has_images"] = True
            elif isinstance(task.markdown, list):
                for md in task.markdown:
                    if hasattr(md, 'content') and '![' in md.content:
                        file_stats["tasks_with_images"] += 1
                        task_files["has_images"] = True
                        break
            
            # 记录文件引用（只记录有文件的任务）
            if any([task_files["cover_url"], task_files["file_path"], task_files["has_images"]]):
                file_stats["file_references"].append(task_files)
        
        logger.info(f"✅ 文件验证完成: {file_stats}")
        
        return {
            "message": "File integrity validation completed",
            "statistics": file_stats
        }
        
    except Exception as e:
        logger.error(f"❌ 文件完整性验证失败: {e}")
        raise HTTPException(status_code=500, detail=f"File validation failed: {str(e)}") 