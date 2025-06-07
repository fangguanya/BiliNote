# B站合集处理功能改进文档

## 项目简介

本次改进基于 [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) 项目的API文档，大幅增强了B站合集的处理能力，支持更多合集类型，并集成了登录cookie状态管理。

## 改进内容概览

### 1. 新增Cookie状态管理支持

#### 功能特点
- 🍪 **自动cookie注入**: 所有B站API请求自动使用保存的登录cookie
- 🔐 **权限访问**: 支持访问私人收藏夹、稍后再看等需要登录的内容
- 🎫 **会员内容**: 支持大会员专享内容的访问
- 🔄 **统一管理**: 与现有的cookie管理系统无缝集成

#### 技术实现
```python
# 集成CookieConfigManager
from app.services.cookie_manager import CookieConfigManager
cookie_manager = CookieConfigManager()

# API请求自动添加cookie
bilibili_cookie = cookie_manager.get("bilibili")
if bilibili_cookie:
    headers['Cookie'] = bilibili_cookie
```

### 2. 新增合集类型支持

#### 支持的合集类型

| 合集类型 | URL模式 | 登录要求 | 说明 |
|---------|---------|----------|------|
| 收藏夹 | `favlist?fid=xxx` | 私人收藏夹需要 | 支持公开和私人收藏夹 |
| 个人合集 | `collectiondetail?sid=xxx` | 部分需要 | UP主创建的视频合集 |
| 系列视频 | `seriesdetail?sid=xxx` | 部分需要 | 系列化内容 |
| 稍后再看 | `watchlater` | **必须** | 个人稍后再看列表 |
| 番剧系列 | `bangumi/play/ss{id}` | 部分需要 | 番剧/电影系列 |
| 番剧媒体 | `bangumi/media/md{id}` | 部分需要 | 番剧媒体页面 |
| 多分P视频 | `video/BV{id}` | 否 | 多分P视频自动识别 |
| UGC合集 | `video/BV{id}` | 否 | 用户创建的合集 |
| 用户投稿 | `space.bilibili.com/{uid}/video` | 否 | 用户所有投稿 |
| 频道首页 | `channel/index` | 否 | 频道主页内容 |

#### 新增API端点支持

##### 稍后再看API
```python
def _fetch_bilibili_watchlater_videos(api_url: str):
    """获取B站稍后再看视频列表"""
    # API: https://api.bilibili.com/x/v2/history/toview
    # 需要登录cookie
```

##### 番剧系列API
```python
def _fetch_bilibili_bangumi_videos(api_url: str):
    """获取B站番剧视频列表"""
    # API: https://api.bilibili.com/pgc/web/season/section
    # 支持正片、花絮等多种类型
```

##### 番剧媒体API
```python
def _fetch_bilibili_bangumi_by_media_id(api_url: str, max_videos: int):
    """通过媒体ID获取B站番剧视频列表"""
    # API: https://api.bilibili.com/pgc/review/user
    # 先获取season_id，再获取剧集列表
```

### 3. 增强的合集检测逻辑

#### 改进的检测算法

##### 单视频合集检测
```python
def is_video_part_of_collection(url: str) -> bool:
    """检查单个B站视频是否属于某个合集"""
    # 1. UGC合集检测 (ugc_season字段)
    # 2. 多分P视频检测 (pages数量)
    # 3. 番剧/电影检测 (season字段)
    # 4. 系列视频检测 (标题关键词)
    # 5. 相关视频检测 (Related字段)
```

##### 关键词扩展
```python
series_keywords = [
    '合集', '系列', '第一集', '第二集', 'P1', 'P2', 
    '上篇', '下篇', '（一）', '（二）', '【合集】', 
    '【系列】', '全集', '连载', '番外', 'EP', 'ep'
]
```

### 4. API参考来源

本次改进严格参考了 [bilibili-API-collect](https://socialsisteryi.github.io/bilibili-API-collect/) 项目的API文档，主要使用了以下API：

- **视频信息**: `https://api.bilibili.com/x/web-interface/view`
- **合集信息**: `https://api.bilibili.com/x/polymer/space/seasons_archives_list`
- **收藏夹**: `https://api.bilibili.com/x/v3/fav/resource/list`
- **稍后再看**: `https://api.bilibili.com/x/v2/history/toview`
- **番剧系列**: `https://api.bilibili.com/pgc/web/season/section`
- **番剧媒体**: `https://api.bilibili.com/pgc/review/user`

## 使用方法

### 1. 基础使用

```python
from app.utils.url_parser import (
    identify_platform, 
    is_collection_url, 
    extract_collection_videos,
    is_video_part_of_collection
)

# 1. 识别平台
platform = identify_platform(url)

# 2. 检测合集类型
is_collection = is_collection_url(url, platform)

# 3. 检测单视频是否属于合集（仅B站）
is_part_of_collection = is_video_part_of_collection(url)

# 4. 提取合集视频列表
videos = extract_collection_videos(url, platform, max_videos=50)
```

### 2. Cookie管理

```python
from app.services.cookie_manager import CookieConfigManager

cookie_manager = CookieConfigManager()

# 获取B站cookie（通常通过前端扫码登录获得）
bilibili_cookie = cookie_manager.get("bilibili")

# 设置cookie
cookie_manager.set("bilibili", cookie_string)
```

### 3. 演示程序

运行演示程序查看完整功能：

```bash
cd backend
python examples/bilibili_collection_demo.py
```

## 技术特点

### 1. 渐进式增强
- 🔧 **向后兼容**: 现有功能完全兼容
- 📈 **功能扩展**: 新增功能不影响原有逻辑
- 🛡️ **错误处理**: 完善的异常处理和降级机制

### 2. 日志与监控
- 📝 **详细日志**: 每个步骤都有详细的日志记录
- 🔍 **调试信息**: 便于问题排查和性能优化
- 📊 **状态监控**: 实时反馈处理进度

### 3. 配置灵活性
- ⚙️ **参数可调**: max_videos、timeout等参数可配置
- 🔄 **自动重试**: 网络请求失败自动重试
- 🎯 **精确控制**: 支持精确的URL匹配和ID提取

## 安全与性能

### 1. 安全特性
- 🔒 **Cookie安全**: 敏感信息不记录在日志中
- 🛡️ **请求限制**: 合理的请求频率控制
- 🔐 **权限校验**: 严格的权限检查机制

### 2. 性能优化
- ⚡ **并发请求**: 支持并发获取合集信息
- 📦 **缓存机制**: 避免重复API调用
- ⏱️ **超时控制**: 合理的超时设置

## 注意事项

### 1. 登录要求
- 稍后再看：**必须登录**
- 私人收藏夹：**必须登录且有权限**
- 大会员内容：**需要有效的大会员状态**
- 部分番剧：**可能需要大会员**

### 2. 使用限制
- 遵守B站API使用规范
- 避免频繁请求导致IP被限制
- 尊重内容创作者的权益

### 3. 隐私保护
- 不记录敏感的cookie信息到日志
- 不缓存个人隐私相关数据
- 建议定期更新登录状态

## 参考资源

- [bilibili-API-collect 项目](https://github.com/SocialSisterYi/bilibili-API-collect)
- [API文档网站](https://socialsisteryi.github.io/bilibili-API-collect/)
- [B站开放平台](https://openhome.bilibili.com/)

## 更新日志

### v1.0.0 (2025-01-19)
- ✨ 集成Cookie状态管理
- ✨ 新增9种合集类型支持
- ✨ 优化合集检测算法
- ✨ 添加番剧系列支持
- ✨ 新增稍后再看功能
- 📝 完善文档和示例代码
- 🐛 修复多分P视频标题重复问题

---

*本文档基于 bilibili-API-collect 项目的API文档编写，感谢该项目维护者的贡献。* 