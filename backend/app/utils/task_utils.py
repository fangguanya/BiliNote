import os
import json
import time
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 使用绝对路径计算存储目录
NOTE_OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "note_results"))

def save_original_request_data(task_id: str, request_data: dict):
    """保存原始请求数据到持久化存储"""
    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    
    try:
        # 添加时间戳和任务ID
        request_data_with_meta = {
            "task_id": task_id,
            "created_at": time.time(),
            "created_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "original_request": request_data
        }
        
        # 保存到 {task_id}.request.json 文件
        request_file_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.request.json")
        with open(request_file_path, "w", encoding="utf-8") as f:
            json.dump(request_data_with_meta, f, ensure_ascii=False, indent=2)
            
        logger.info(f"✅ 原始请求数据已保存: {task_id}")
        
    except Exception as e:
        logger.error(f"❌ 保存原始请求数据失败: {task_id}, {e}")


def load_original_request_data(task_id: str) -> dict:
    """从持久化存储加载原始请求数据"""
    try:
        request_file_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.request.json")
        
        if os.path.exists(request_file_path):
            with open(request_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 返回原始请求数据
            original_request = data.get("original_request", {})
            logger.info(f"✅ 成功加载原始请求数据: {task_id}")
            return original_request
        else:
            logger.warning(f"⚠️ 原始请求数据文件不存在: {task_id}")
            return {}
            
    except Exception as e:
        logger.error(f"❌ 加载原始请求数据失败: {task_id}, {e}")
        return {} 