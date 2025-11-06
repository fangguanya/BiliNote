# Third Party Libraries

本目录包含集成到项目中的第三方库源码。

## 📁 目录结构

```
third_party/
├── baidupcs_py/              # BaiduPCS-Py 源码
│   ├── baidupcs/             # 核心 API
│   ├── commands/             # 命令行工具
│   ├── common/               # 通用工具
│   └── app/                  # 应用层
├── baidupcs_api.py           # API 下载器（绕过命令行工具 bug）
└── README.md                 # 本文件
```

## 🔄 更新说明

### baidupcs_py/

**来源**: https://github.com/PeterDing/BaiduPCS-Py

**版本**: 从系统已安装的 `baidupcs-py` 包复制

**更新方法**:
```bash
# 1. 更新系统中的 baidupcs-py
pip install --upgrade baidupcs-py

# 2. 获取安装路径
python -c "import baidupcs_py; import os; print(os.path.dirname(baidupcs_py.__file__))"

# 3. 复制到项目中（覆盖）
# Windows:
xcopy /E /I /Y "<安装路径>" "backend\app\third_party\baidupcs_py"

# Linux/Mac:
cp -r <安装路径>/* backend/app/third_party/baidupcs_py/
```

**修改说明**:
- ⚠️ 未修改任何源码
- 直接使用官方源码，通过 `baidupcs_downloader.py` 封装使用

### baidupcs_api.py

**用途**: BaiduPCS API 下载器

**特性**:
- 直接使用 Python API，避免命令行工具的长路径问题
- 自动简化长文件名（前50字符 + MD5哈希）
- 使用 `api.list()` 避免长路径问题
- 使用 `MeDownloader` 进行实际下载
- 完整的错误处理

**修改说明**:
- ✅ 这是我们自己编写的封装代码
- 可以根据需要修改和优化
- 与 `app/downloaders/baidupcs_downloader.py` 不同（那个使用命令行工具）

## 📝 使用示例

```python
from app.third_party.baidupcs_api import BaiduPCSDownloader

# 创建下载器（自动加载已登录账号）
downloader = BaiduPCSDownloader()

# 下载文件
result = downloader.download_file(
    remote_path="/path/to/file.mp4",
    local_dir="./downloads",
    concurrency=5
)

if result['success']:
    print(f"下载成功: {result['local_path']}")
    print(f"文件大小: {result['file_size']} 字节")
```

## 🔗 相关文档

- [问题诊断报告](../../BAIDUPCS_LONG_PATH_ISSUE.md)
- [集成指南](../../BAIDUPCS_FIX_INTEGRATION.md)
- [BaiduPCS-Py 官方文档](https://github.com/PeterDing/BaiduPCS-Py)

## ⚠️ 注意事项

1. **不要修改 `baidupcs_py/` 目录中的代码**
   - 这是第三方库的源码，应保持与官方同步
   - 如需修改功能，请在 `baidupcs_downloader.py` 中封装

2. **更新前先测试**
   - 更新 `baidupcs_py/` 后，确保 `baidupcs_downloader.py` 仍然正常工作
   - 运行测试用例验证功能

3. **保留 `__pycache__` 目录**
   - 这些是 Python 编译后的缓存文件
   - 可以加快导入速度
   - Git 已配置忽略这些文件

## 📊 版本信息

| 组件 | 版本 | 更新日期 |
|------|------|---------|
| baidupcs_py | 从系统安装 | 2025-11-06 |
| baidupcs_downloader | 1.0.0 | 2025-11-06 |

## 🐛 已知问题

- BaiduPCS-Py 命令行工具无法处理长路径（已通过 API 绕过）
- 大文件下载可能需要较长时间
- 暂不支持断点续传

## 📮 反馈

如有问题或建议，请查看项目主 README 或提交 Issue。

