#!/usr/bin/env python3
"""
强制重启任务脚本
用于强制清理并重新开始指定的任务
"""

import requests
import sys
import json

def force_restart_task(task_id: str, base_url: str = "http://localhost:8001"):
    """
    强制重启指定任务
    
    Args:
        task_id: 任务ID
        base_url: 后端服务地址
    """
    try:
        print(f"🔥 开始强制重启任务: {task_id}")
        
        # 调用强制重启接口
        url = f"{base_url}/force_restart_task/{task_id}"
        response = requests.post(url)
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get("code") == 0:
                data = result.get("data", {})
                print(f"✅ 强制重启成功!")
                print(f"📋 任务标题: {data.get('title', '未知')}")
                print(f"🔗 视频URL: {data.get('video_url', '未知')}")
                print(f"🧹 清理文件数: {len(data.get('cleaned_files', []))}")
                
                cleaned_files = data.get('cleaned_files', [])
                if cleaned_files:
                    print(f"🗑️ 已清理的文件:")
                    for file in cleaned_files:
                        print(f"   - {file}")
                
                print(f"💫 新任务已创建，状态：PENDING")
                return True
            else:
                print(f"❌ 强制重启失败: {result.get('message', '未知错误')}")
                return False
        else:
            print(f"❌ HTTP请求失败: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        return False

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python force_restart_task.py <task_id> [base_url]")
        print("示例: python force_restart_task.py 27dda469-bdd5-4887-aa5c-0d9567228fa9")
        print("示例: python force_restart_task.py 27dda469-bdd5-4887-aa5c-0d9567228fa9 http://localhost:8001")
        sys.exit(1)
    
    task_id = sys.argv[1]
    base_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8001"
    
    print(f"🎯 目标任务ID: {task_id}")
    print(f"🌐 后端地址: {base_url}")
    print("-" * 50)
    
    success = force_restart_task(task_id, base_url)
    
    if success:
        print("-" * 50)
        print("🎉 任务强制重启完成! 请检查任务队列状态。")
        sys.exit(0)
    else:
        print("-" * 50)
        print("💥 任务强制重启失败! 请检查错误信息。")
        sys.exit(1)

if __name__ == "__main__":
    main() 