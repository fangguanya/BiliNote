#!/usr/bin/env python3
"""
直接强制重启任务脚本
直接在代码环境中操作，不需要HTTP服务
"""

import json
import os
import sys
import time
import glob
from pathlib import Path

# 添加backend路径到sys.path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

def force_restart_task_direct(task_id: str):
    """
    直接强制重启指定任务（不需要HTTP服务）
    
    Args:
        task_id: 任务ID
    """
    try:
        print(f"🔥 开始直接强制重启任务: {task_id}")
        
        # 设置路径
        NOTE_OUTPUT_DIR = "backend/note_results"
        os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
        
        # 1. 首先尝试从音频文件获取原始任务数据
        audio_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_audio.json")
        task_data = None
        
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
                    task_data = {
                        'video_url': video_url,
                        'platform': platform,
                        'quality': 'fast',  # DownloadQuality.AUDIO
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
                    
                    print(f"✅ 从音频文件获取任务数据成功: {title}")
                    print(f"🔗 视频URL: {video_url}")
                    
            except Exception as e:
                print(f"❌ 读取音频文件失败: {task_id}, {e}")
        
        # 如果没有获取到任务数据，返回错误
        if not task_data:
            print(f"❌ 无法获取任务数据，无法重新开始: {task_id}")
            print(f"📁 音频文件路径: {audio_path}")
            print(f"📁 音频文件存在: {os.path.exists(audio_path)}")
            return False
        
        # 2. 清理所有相关文件
        print(f"🧹 开始清理任务相关文件: {task_id}")
        
        # 清理模式列表
        cleanup_patterns = [
            f"{task_id}.json",
            f"{task_id}.status.json", 
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
                        print(f"🗑️ 已删除文件: {os.path.basename(file_path)}")
                except Exception as e:
                    print(f"⚠️ 删除文件失败: {os.path.basename(file_path)}, {e}")
        
        # 3. 创建一个新的任务请求文件，供后续处理
        restart_request = {
            "task_id": task_id,
            "task_data": task_data,
            "restart_time": time.time(),
            "status": "RESTART_REQUESTED",
            "cleaned_files": cleaned_files
        }
        
        restart_file = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_restart_request.json")
        with open(restart_file, "w", encoding="utf-8") as f:
            json.dump(restart_request, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 强制重启准备完成: {task_id}")
        print(f"📋 任务详情: {task_data.get('title', '未知标题')}")
        print(f"🧹 清理了 {len(cleaned_files)} 个文件")
        print(f"📄 重启请求文件已创建: {restart_file}")
        
        # 输出任务信息
        print("-" * 50)
        print("📋 任务信息:")
        print(f"   标题: {task_data.get('title', '未知')}")
        print(f"   URL: {task_data.get('video_url', '未知')}")
        print(f"   平台: {task_data.get('platform', '未知')}")
        print(f"   模型: {task_data.get('model_name', '未知')}")
        print(f"   提供者: {task_data.get('provider_id', '未知')}")
        print(f"   风格: {task_data.get('style', '未知')}")
        
        if cleaned_files:
            print("🗑️ 已清理的文件:")
            for file in cleaned_files:
                print(f"   - {file}")
        
        print("-" * 50)
        print("💡 接下来需要做的:")
        print("1. 确保后端服务正在运行")
        print("2. 通过前端重新提交这个任务，或者")
        print("3. 使用生成的重启请求文件来重新创建任务")
        
        return True
        
    except Exception as e:
        print(f"❌ 强制重启失败: {e}")
        return False

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python direct_restart_task.py <task_id>")
        print("示例: python direct_restart_task.py 27dda469-bdd5-4887-aa5c-0d9567228fa9")
        sys.exit(1)
    
    task_id = sys.argv[1]
    
    print(f"🎯 目标任务ID: {task_id}")
    print("-" * 50)
    
    success = force_restart_task_direct(task_id)
    
    if success:
        print("🎉 任务强制重启准备完成!")
        sys.exit(0)
    else:
        print("💥 任务强制重启失败!")
        sys.exit(1)

if __name__ == "__main__":
    main() 