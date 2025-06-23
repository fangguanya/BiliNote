
"""
Cursor 编辑器卡死问题修复脚本
自动诊断和修复常见的 Cursor 编辑器问题
"""

import os
import sys
import shutil
import psutil
import subprocess
import platform
import json
from pathlib import Path
from typing import List, Dict, Optional

class CursorFixer:
    """Cursor 编辑器修复工具"""
    
    def __init__(self):
        self.system = platform.system().lower()
        self.config_paths = self._get_config_paths()
        self.processes = []
    
    def _get_config_paths(self) -> Dict[str, Path]:
        """获取配置文件路径"""
        if self.system == "windows":
            base = Path(os.environ.get("APPDATA", "")) / "Cursor"
        elif self.system == "darwin":  # macOS
            base = Path.home() / "Library" / "Application Support" / "Cursor"
        else:  # Linux
            base = Path.home() / ".config" / "Cursor"
        
        return {
            "base": base,
            "user": base / "User",
            "workspace": base / "User" / "workspaceStorage",
            "logs": base / "User" / "logs",
            "cache": base / "CachedData",
            "settings": base / "User" / "settings.json"
        }
    
    def check_system_resources(self) -> Dict[str, float]:
        """检查系统资源使用情况"""
        print("🔍 检查系统资源...")
        
        # 获取系统信息
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        disk = psutil.disk_usage('/')
        
        # 查找 Cursor 进程
        cursor_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
            try:
                if 'cursor' in proc.info['name'].lower():
                    cursor_processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        self.processes = cursor_processes
        
        stats = {
            "memory_total": memory.total / (1024**3),  # GB
            "memory_used": memory.used / (1024**3),
            "memory_percent": memory.percent,
            "cpu_percent": cpu_percent,
            "disk_free": disk.free / (1024**3),
            "cursor_processes": len(cursor_processes)
        }
        
        print(f"📊 系统资源状况:")
        print(f"   内存: {stats['memory_used']:.1f}GB / {stats['memory_total']:.1f}GB ({stats['memory_percent']:.1f}%)")
        print(f"   CPU: {stats['cpu_percent']:.1f}%")
        print(f"   磁盘剩余: {stats['disk_free']:.1f}GB")
        print(f"   Cursor 进程数: {stats['cursor_processes']}")
        
        return stats
    
    def kill_cursor_processes(self) -> bool:
        """强制结束 Cursor 进程"""
        print("🔪 强制结束 Cursor 进程...")
        
        killed_count = 0
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if 'cursor' in proc.info['name'].lower():
                    proc.terminate()
                    proc.wait(timeout=5)
                    killed_count += 1
                    print(f"   已结束进程: {proc.info['name']} (PID: {proc.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                continue
        
        print(f"✅ 共结束 {killed_count} 个进程")
        return killed_count > 0
    
    def clear_cache(self) -> bool:
        """清理缓存文件"""
        print("🗑️ 清理缓存文件...")
        
        cleared_items = []
        
        # 要清理的目录
        dirs_to_clear = [
            self.config_paths["workspace"],
            self.config_paths["logs"],
            self.config_paths["cache"]
        ]
        
        for dir_path in dirs_to_clear:
            if dir_path.exists():
                try:
                    shutil.rmtree(dir_path)
                    cleared_items.append(str(dir_path))
                    print(f"   已清理: {dir_path}")
                except Exception as e:
                    print(f"   清理失败 {dir_path}: {e}")
        
        # 清理临时文件
        temp_patterns = [
            "/tmp/cursor-*",
            "/tmp/vscode-*", 
            os.path.expandvars("$TEMP/cursor-*")
        ]
        
        for pattern in temp_patterns:
            try:
                for path in Path(pattern).parent.glob(Path(pattern).name):
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    cleared_items.append(str(path))
            except Exception:
                continue
        
        print(f"✅ 共清理 {len(cleared_items)} 个项目")
        return len(cleared_items) > 0
    
    def backup_settings(self) -> Optional[str]:
        """备份当前设置"""
        print("💾 备份当前设置...")
        
        settings_file = self.config_paths["settings"]
        if not settings_file.exists():
            print("   没有找到设置文件")
            return None
        
        backup_file = settings_file.with_suffix(".json.backup")
        try:
            shutil.copy2(settings_file, backup_file)
            print(f"   设置已备份到: {backup_file}")
            return str(backup_file)
        except Exception as e:
            print(f"   备份失败: {e}")
            return None
    
    def optimize_settings(self) -> bool:
        """优化设置文件"""
        print("⚙️ 优化设置文件...")
        
        optimized_settings = {
            # 内存优化
            "files.watcherExclude": {
                "**/.git/objects/**": True,
                "**/.git/subtree-cache/**": True,
                "**/node_modules/**": True,
                "**/dist/**": True,
                "**/build/**": True,
                "**/.vscode/**": True
            },
            
            # 性能优化
            "editor.quickSuggestions": {
                "other": False,
                "comments": False,
                "strings": False
            },
            "editor.suggestOnTriggerCharacters": False,
            "editor.parameterHints.enabled": False,
            "editor.hover.delay": 1000,
            
            # 语言服务优化
            "typescript.suggest.autoImports": False,
            "typescript.updateImportsOnFileMove.enabled": "never",
            "typescript.preferences.includePackageJsonAutoImports": "off",
            
            # AI 功能优化
            "cursor.ai.enableAutoCompletion": False,
            "cursor.ai.enableInlineCompletion": False,
            
            # 文件处理优化
            "files.maxMemoryForLargeFilesMB": 2048,
            "search.maxResults": 10000,
            "search.smartCase": False,
            
            # 界面优化
            "workbench.startupEditor": "none",
            "window.restoreWindows": "none",
            "extensions.autoUpdate": False
        }
        
        try:
            settings_file = self.config_paths["settings"]
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 读取现有设置
            existing_settings = {}
            if settings_file.exists():
                try:
                    with open(settings_file, 'r', encoding='utf-8') as f:
                        existing_settings = json.load(f)
                except Exception:
                    pass
            
            # 合并设置
            existing_settings.update(optimized_settings)
            
            # 写入优化后的设置
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(existing_settings, f, indent=2, ensure_ascii=False)
            
            print("   设置文件已优化")
            return True
            
        except Exception as e:
            print(f"   优化失败: {e}")
            return False
    
    def check_extensions(self) -> List[str]:
        """检查问题扩展"""
        print("🔌 检查扩展...")
        
        # 常见问题扩展
        problematic_extensions = [
            "ms-python.python",  # Python 扩展可能消耗大量内存
            "ms-vscode.cpptools",  # C++ 扩展
            "ms-dotnettools.csharp",  # C# 扩展
            "golang.go",  # Go 扩展
            "rust-lang.rust",  # Rust 扩展
        ]
        
        found_extensions = []
        
        try:
            # 尝试获取扩展列表
            result = subprocess.run(
                ["cursor", "--list-extensions"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                installed_extensions = result.stdout.strip().split('\n')
                for ext in problematic_extensions:
                    if ext in installed_extensions:
                        found_extensions.append(ext)
                        print(f"   发现可能有问题的扩展: {ext}")
            
        except Exception as e:
            print(f"   无法获取扩展列表: {e}")
        
        return found_extensions
    
    def start_cursor_safe_mode(self) -> bool:
        """以安全模式启动 Cursor"""
        print("🚀 以安全模式启动 Cursor...")
        
        try:
            subprocess.Popen([
                "cursor",
                "--disable-extensions",
                "--disable-workspace-trust",
                "--no-sandbox"
            ])
            print("   Cursor 已以安全模式启动")
            return True
        except Exception as e:
            print(f"   启动失败: {e}")
            return False
    
    def run_full_fix(self) -> bool:
        """运行完整修复流程"""
        print("🔧 开始完整修复流程...\n")
        
        # 1. 检查系统资源
        stats = self.check_system_resources()
        
        # 2. 强制结束进程
        self.kill_cursor_processes()
        
        # 3. 备份设置
        backup_path = self.backup_settings()
        
        # 4. 清理缓存
        self.clear_cache()
        
        # 5. 优化设置
        self.optimize_settings()
        
        # 6. 检查扩展
        problematic_exts = self.check_extensions()
        
        # 7. 以安全模式启动
        self.start_cursor_safe_mode()
        
        print(f"\n✅ 修复完成!")
        print(f"📋 修复摘要:")
        print(f"   - 系统内存使用: {stats['memory_percent']:.1f}%")
        print(f"   - 结束的进程数: {stats['cursor_processes']}")
        print(f"   - 设置备份: {'是' if backup_path else '否'}")
        print(f"   - 问题扩展数: {len(problematic_exts)}")
        
        if problematic_exts:
            print(f"\n⚠️ 建议禁用以下扩展:")
            for ext in problematic_exts:
                print(f"   - {ext}")
        
        print(f"\n💡 建议:")
        print(f"   - 如果问题仍然存在，请考虑重新安装 Cursor")
        print(f"   - 定期清理缓存和工作区")
        print(f"   - 避免同时打开过多大文件")
        
        return True


def main():
    """主函数"""
    print("🚀 Cursor 编辑器修复工具")
    print("=" * 50)
    
    fixer = CursorFixer()
    
    try:
        choice = input("\n选择操作:\n1. 快速修复\n2. 完整诊断和修复\n3. 仅清理缓存\n4. 仅结束进程\n请输入数字 (1-4): ")
        
        if choice == "1":
            fixer.kill_cursor_processes()
            fixer.clear_cache()
            fixer.start_cursor_safe_mode()
        elif choice == "2":
            fixer.run_full_fix()
        elif choice == "3":
            fixer.clear_cache()
        elif choice == "4":
            fixer.kill_cursor_processes()
        else:
            print("无效选择")
            return
        
        print("\n✅ 操作完成!")
        
    except KeyboardInterrupt:
        print("\n\n❌ 操作被用户取消")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")

if __name__ == "__main__":
    main()
