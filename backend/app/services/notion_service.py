import os
import re
import requests
import mimetypes
from typing import Optional, Dict, Any, List
from notion_client import Client
from datetime import datetime
from urllib.parse import urlparse
from app.utils.logger import get_logger
from app.models.notes_model import NoteResult

logger = get_logger(__name__)

class NotionService:
    """Notion集成服务"""
    
    def __init__(self, token: str):
        """
        初始化Notion客户端
        
        Args:
            token: Notion集成令牌
        """
        try:
            self.token = token  # 保存token用于直接API调用
            self.client = Client(auth=token)
            logger.info("Notion客户端初始化成功")
        except Exception as e:
            logger.error(f"Notion客户端初始化失败: {e}")
            raise ValueError(f"Notion客户端初始化失败: {e}")
    
    def test_connection(self) -> bool:
        """
        测试Notion连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 通过获取用户信息来测试连接
            self.client.users.me()
            logger.info("Notion连接测试成功")
            return True
        except Exception as e:
            logger.error(f"Notion连接测试失败: {e}")
            return False
    
    def list_databases(self) -> List[Dict[str, Any]]:
        """
        获取可用的数据库列表
        
        Returns:
            List[Dict]: 数据库列表
        """
        try:
            response = self.client.search(
                filter={"property": "object", "value": "database"}
            )
            
            databases = []
            for db in response.get("results", []):
                databases.append({
                    "id": db["id"],
                    "title": self._extract_title(db.get("title", [])),
                    "url": db.get("url", ""),
                    "created_time": db.get("created_time", ""),
                    "last_edited_time": db.get("last_edited_time", "")
                })
            
            logger.info(f"成功获取 {len(databases)} 个数据库")
            return databases
        except Exception as e:
            logger.error(f"获取数据库列表失败: {e}")
            return []
    
    def _get_database_properties(self, database_id: str) -> Dict[str, Any]:
        """
        获取数据库的属性结构
        
        Args:
            database_id: 数据库ID
            
        Returns:
            Dict: 数据库属性信息
        """
        try:
            response = self.client.databases.retrieve(database_id)
            return response.get("properties", {})
        except Exception as e:
            logger.error(f"获取数据库属性失败: {e}")
            return {}

    def create_page_in_database(self, database_id: str, note_result: NoteResult) -> Dict[str, Any]:
        """
        在指定数据库中创建页面
        
        Args:
            database_id: 数据库ID
            note_result: 笔记结果数据
            
        Returns:
            Dict: 创建结果
        """
        try:
            # 获取数据库属性结构
            db_properties = self._get_database_properties(database_id)
            
            # 准备页面属性
            properties = {}
            
            # 寻找标题属性并设置
            title_property = None
            for prop_name, prop_config in db_properties.items():
                if prop_config.get("type") == "title":
                    title_property = prop_name
                    break
            
            if title_property:
                properties[title_property] = {
                    "title": [
                        {
                            "text": {
                                "content": note_result.audio_meta.title or "未命名笔记"
                            }
                        }
                    ]
                }
            else:
                # 如果没有找到标题属性，使用Name作为默认
                properties["Name"] = {
                    "title": [
                        {
                            "text": {
                                "content": note_result.audio_meta.title or "未命名笔记"
                            }
                        }
                    ]
                }
            
            # 智能匹配其他属性
            for prop_name, prop_config in db_properties.items():
                prop_type = prop_config.get("type")
                prop_name_lower = prop_name.lower()
                
                # 匹配时长属性
                if (prop_type == "number" and 
                    ("时长" in prop_name or "duration" in prop_name_lower or "长度" in prop_name) and
                    hasattr(note_result.audio_meta, 'duration') and note_result.audio_meta.duration):
                    properties[prop_name] = {
                        "number": note_result.audio_meta.duration
                    }
                
                # 匹配平台属性
                elif (prop_type == "select" and 
                      ("平台" in prop_name or "platform" in prop_name_lower or "来源" in prop_name) and
                      hasattr(note_result.audio_meta, 'platform') and note_result.audio_meta.platform):
                    properties[prop_name] = {
                        "select": {
                            "name": note_result.audio_meta.platform
                        }
                    }
                
                # 匹配URL属性
                elif (prop_type == "url" and 
                      ("url" in prop_name_lower or "链接" in prop_name or "地址" in prop_name) and
                      hasattr(note_result.audio_meta, 'url') and note_result.audio_meta.url):
                    properties[prop_name] = {
                        "url": note_result.audio_meta.url
                    }
                
                # 匹配日期属性
                elif (prop_type == "date" and 
                      ("日期" in prop_name or "date" in prop_name_lower or "创建" in prop_name)):
                    from datetime import datetime
                    properties[prop_name] = {
                        "date": {
                            "start": datetime.now().isoformat()
                        }
                    }
            
            # 准备页面内容
            children = self._markdown_to_notion_blocks(note_result.markdown)
            
            # 创建页面
            response = self.client.pages.create(
                parent={"database_id": database_id},
                properties=properties,
                children=children
            )
            
            logger.info(f"成功创建Notion页面: {response['id']}")
            return {
                "success": True,
                "page_id": response["id"],
                "url": response["url"],
                "title": note_result.audio_meta.title
            }
            
        except Exception as e:
            logger.error(f"创建Notion页面失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_standalone_page(self, note_result: NoteResult, parent_page_id: Optional[str] = None) -> Dict[str, Any]:
        """
        创建独立页面（不在数据库中）
        
        Args:
            note_result: 笔记结果数据
            parent_page_id: 父页面ID（可选）
            
        Returns:
            Dict: 创建结果
        """
        try:
            # 准备页面属性
            properties = {
                "title": [
                    {
                        "text": {
                            "content": note_result.audio_meta.title or "未命名笔记"
                        }
                    }
                ]
            }
            
            # 设置父页面
            if parent_page_id:
                parent = {"page_id": parent_page_id}
            else:
                # 如果没有指定父页面，需要有一个workspace
                parent = {"type": "workspace", "workspace": True}
            
            # 准备页面内容
            children = self._markdown_to_notion_blocks(note_result.markdown)
            
            # 创建页面
            response = self.client.pages.create(
                parent=parent,
                properties=properties,
                children=children
            )
            
            logger.info(f"成功创建独立Notion页面: {response['id']}")
            return {
                "success": True,
                "page_id": response["id"],
                "url": response["url"],
                "title": note_result.audio_meta.title
            }
            
        except Exception as e:
            logger.error(f"创建独立Notion页面失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _extract_title(self, title_array: List[Dict]) -> str:
        """
        从Notion标题数组中提取文本
        
        Args:
            title_array: Notion标题数组
            
        Returns:
            str: 提取的标题文本
        """
        if not title_array:
            return "未命名"
        
        title_text = ""
        for item in title_array:
            if item.get("type") == "text":
                title_text += item.get("text", {}).get("content", "")
                
        return title_text or "未命名"
    
    def _is_valid_url(self, url: str) -> bool:
        """
        验证URL是否有效
        
        Args:
            url: 要验证的URL
            
        Returns:
            bool: URL是否有效
        """
        try:
            # 排除一些明显无效的URL格式
            if not url or url.strip() == "":
                return False
            
            # 排除attachment:协议和其他特殊协议
            if url.startswith(('attachment:', 'data:', 'blob:')):
                logger.warning(f"跳过特殊协议URL: {url}")
                return False
            
            result = urlparse(url)
            # 检查是否有有效的scheme和netloc（对于http/https）或者是相对路径
            if result.scheme in ('http', 'https'):
                return bool(result.netloc)
            elif result.scheme == '':
                # 相对路径也认为是有效的
                return bool(result.path)
            else:
                # 其他协议需要有path
                return bool(result.path)
        except Exception as e:
            logger.warning(f"URL验证失败: {url}, 错误: {e}")
            return False

    def upload_file_to_notion(self, file_path: str, filename: str = None) -> Optional[str]:
        """
        上传文件到Notion并返回file_upload_id
        
        Args:
            file_path: 文件路径（本地路径或URL）
            filename: 文件名（可选）
            
        Returns:
            str: file_upload_id，失败时返回None
        """
        try:
            # 首先检查和处理特殊协议
            if file_path.startswith(('attachment:', 'data:', 'blob:')):
                logger.warning(f"⚠️ 不支持的文件协议: {file_path}")
                return None
            
            # 首先获取文件内容和类型信息，用于创建File Upload对象
            file_content = None
            content_type = None
            final_filename = filename
            
            if file_path.startswith(('http://', 'https://')):
                # 网络文件
                logger.info(f"正在下载网络文件: {file_path}")
                file_response = requests.get(file_path)
                if file_response.status_code == 200:
                    file_content = file_response.content
                    content_type = file_response.headers.get('content-type', 'application/octet-stream')
                    if not final_filename:
                        final_filename = file_path.split('/')[-1]
                else:
                    logger.error(f"下载网络文件失败: {file_path}, 状态码: {file_response.status_code}")
                    return None
            else:
                # 本地文件处理
                original_path = file_path
                
                # 处理相对路径
                if file_path.startswith('./'):
                    file_path = file_path[2:]
                if file_path.startswith('/static/'):
                    file_path = file_path[1:]  # 移除开头的 /，变成 static/...
                
                # 构建完整路径，尝试多种可能的位置
                # 增加更多可能的路径组合以解决从JSON重新加载时的路径问题
                possible_paths = [
                    # 当前工作目录下的路径
                    os.path.join(os.getcwd(), 'backend', file_path),     # backend/static/...
                    os.path.join(os.getcwd(), file_path),                # static/...
                    
                    # 如果路径已经包含static，尝试不同的组合
                    os.path.join(os.getcwd(), 'backend', 'static', file_path.replace('static/', '')),  # backend/static/screenshots/...
                    os.path.join(os.getcwd(), 'static', file_path.replace('static/', '')),             # static/screenshots/...
                    
                    # 如果是screenshots相关路径，尝试直接在static目录下查找
                    os.path.join(os.getcwd(), 'backend', 'static', 'screenshots', os.path.basename(file_path)),
                    os.path.join(os.getcwd(), 'static', 'screenshots', os.path.basename(file_path)),
                    
                    # 绝对路径
                    file_path
                ]
                
                full_path = None
                for i, path in enumerate(possible_paths):
                    logger.debug(f"尝试路径 {i+1}: {path}")
                    if os.path.exists(path):
                        full_path = path
                        logger.info(f"✅ 找到文件在路径 {i+1}: {path}")
                        break
                    else:
                        logger.debug(f"❌ 路径不存在: {path}")
                
                if not full_path or not os.path.exists(full_path):
                    logger.error(f"❌ 本地文件不存在: {original_path}")
                    logger.error(f"📁 当前工作目录: {os.getcwd()}")
                    logger.error(f"🔍 尝试过的所有路径:")
                    for i, path in enumerate(possible_paths):
                        exists = "✅ 存在" if os.path.exists(path) else "❌ 不存在"
                        logger.error(f"  {i+1}. {path} - {exists}")
                    return None
                
                logger.info(f"找到本地文件: {full_path}")
                try:
                    with open(full_path, 'rb') as f:
                        file_content = f.read()
                    content_type = mimetypes.guess_type(full_path)[0] or 'application/octet-stream'
                    if not final_filename:
                        final_filename = os.path.basename(full_path)
                except Exception as e:
                    logger.error(f"读取本地文件失败: {e}")
                    return None
            
            if not file_content:
                logger.error("无法获取文件内容")
                return None
            
            # 步骤1: 创建File Upload对象（提供filename和content_type）
            payload = {
                "filename": final_filename,
                "content_type": content_type
            }
            
            logger.info(f"创建File Upload对象: filename={final_filename}, content_type={content_type}, size={len(file_content)} bytes")
            
            file_upload_response = requests.post(
                "https://api.notion.com/v1/file_uploads",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28"
                },
                json=payload
            )
            
            if file_upload_response.status_code != 200:
                logger.error(f"创建file upload对象失败: {file_upload_response.status_code}, {file_upload_response.text}")
                return None
            
            upload_data = file_upload_response.json()
            file_upload_id = upload_data["id"]
            upload_url = upload_data["upload_url"]
            
            logger.info(f"成功创建file upload对象: {file_upload_id}, upload_url: {upload_url}")
            
            # 步骤2: 上传文件内容
            files = {
                'file': (final_filename, file_content, content_type)
            }
            
            logger.info(f"开始上传文件内容到: {upload_url}")
            
            upload_response = requests.post(
                upload_url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Notion-Version": "2022-06-28"
                    # 注意：不要设置Content-Type，让requests自动处理multipart/form-data
                },
                files=files
            )
            
            logger.info(f"文件上传响应状态码: {upload_response.status_code}")
            
            if upload_response.status_code != 200:
                logger.error(f"上传文件内容失败: {upload_response.status_code}, {upload_response.text}")
                return None
            
            upload_result = upload_response.json()
            logger.info(f"上传结果: {upload_result}")
            
            if upload_result.get("status") == "uploaded":
                logger.info(f"✅ 文件上传成功: {final_filename}, file_upload_id: {file_upload_id}")
                return file_upload_id
            else:
                logger.error(f"❌ 文件上传状态异常: {upload_result.get('status')}, 预期状态: uploaded")
                return None
                
        except Exception as e:
            logger.error(f"上传文件到Notion失败: {e}")
            return None
    
    def _extract_images_from_markdown(self, markdown: str) -> List[Dict[str, str]]:
        """
        从Markdown中提取图片信息，支持带星号前缀的格式
        
        Args:
            markdown: 原始Markdown内容
            
        Returns:
            List[Dict]: 图片信息列表，包含alt_text和image_url
        """
        images = []
        # 支持带星号前缀的图片格式: *![](/static/screenshots/...)
        image_pattern = r'^\*?!\[([^\]]*)\]\(([^)]+)\)$'
        
        for line in markdown.split('\n'):
            line = line.strip()
            match = re.match(image_pattern, line)
            if match:
                alt_text = match.group(1)
                image_url = match.group(2)
                images.append({
                    'alt_text': alt_text,
                    'image_url': image_url,
                    'match_text': match.group(0)
                })
        
        return images

    def _markdown_to_notion_blocks(self, markdown: str) -> List[Dict[str, Any]]:
        """
        将Markdown内容转换为Notion块格式
        
        Args:
            markdown: Markdown内容
            
        Returns:
            List[Dict]: Notion块列表
        """
        blocks = []
        lines = markdown.split('\n')
        current_paragraph = []
        
        for line in lines:
            line = line.strip()
            
            # 空行处理
            if not line:
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                continue
            
            # 图片处理 - 支持带星号前缀和后缀的格式，如: *![](/static/screenshots/...)*
            # 匹配模式: 可选的星号(*) + 图片markdown语法 + 可选的星号(*)
            image_match = re.match(r'^\*?\s*!\[([^\]]*)\]\(([^)]+)\)\s*\*?$', line.strip())
            if image_match:
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                alt_text = image_match.group(1)
                image_url = image_match.group(2)
                
                logger.info(f"🖼️ 处理图片: {image_url}, alt_text: '{alt_text}'")
                logger.debug(f"📁 当前工作目录: {os.getcwd()}")
                
                # 上传图片到Notion并创建图片块
                file_upload_id = self.upload_file_to_notion(image_url)
                if file_upload_id:
                    logger.info(f"✅ 图片上传成功，创建file_upload图片块")
                    blocks.append(self._create_image_block_with_upload(file_upload_id, alt_text))
                else:
                    # 如果上传失败，创建一个带有错误信息的段落而不是外部链接
                    logger.warning(f"⚠️ 图片上传失败，将作为文本段落处理: {image_url}")
                    error_text = f"[图片上传失败: {os.path.basename(image_url)}]"
                    if alt_text:
                        error_text = f"[图片上传失败: {alt_text} - {os.path.basename(image_url)}]"
                    blocks.append(self._create_paragraph_block(error_text))
                continue
            
            # 标题处理
            if line.startswith('#'):
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                # 计算标题级别
                level = len(line) - len(line.lstrip('#'))
                level = min(level, 3)  # Notion最多支持3级标题
                title_text = line.lstrip('#').strip()
                
                if level == 1:
                    blocks.append(self._create_heading_1_block(title_text))
                elif level == 2:
                    blocks.append(self._create_heading_2_block(title_text))
                else:
                    blocks.append(self._create_heading_3_block(title_text))
                continue
            
            # 列表处理
            if line.startswith('- ') or line.startswith('* '):
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                list_text = line[2:].strip()
                blocks.append(self._create_bulleted_list_block(list_text))
                continue
            
            # 数字列表处理
            if re.match(r'^\d+\.\s', line):
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                list_text = re.sub(r'^\d+\.\s', '', line)
                blocks.append(self._create_numbered_list_block(list_text))
                continue
            
            # 代码块处理
            if line.startswith('```'):
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                # 简单处理，这里可以扩展更复杂的代码块逻辑
                continue
            
            # 引用处理
            if line.startswith('>'):
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                quote_text = line[1:].strip()
                blocks.append(self._create_quote_block(quote_text))
                continue
            
            # 普通段落
            current_paragraph.append(line)
        
        # 处理最后的段落
        if current_paragraph:
            blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
        
        return blocks
    
    def _create_paragraph_block(self, text: str) -> Dict[str, Any]:
        """创建段落块，支持链接解析"""
        # 解析链接和普通文本
        rich_text = self._parse_rich_text(text)
        
        return {
            "type": "paragraph",
            "paragraph": {
                "rich_text": rich_text
            }
        }
    
    def _parse_rich_text(self, text: str) -> List[Dict[str, Any]]:
        """解析文本中的链接和格式，返回rich_text数组"""
        rich_text = []
        
        # 匹配Markdown链接格式 [text](url)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        last_end = 0
        
        for match in re.finditer(link_pattern, text):
            # 添加链接前的普通文本
            if match.start() > last_end:
                plain_text = text[last_end:match.start()]
                if plain_text:
                    rich_text.append({
                        "type": "text",
                        "text": {
                            "content": plain_text
                        }
                    })
            
            # 验证并添加链接
            link_text = match.group(1)
            link_url = match.group(2)
            
            if self._is_valid_url(link_url):
                rich_text.append({
                    "type": "text",
                    "text": {
                        "content": link_text,
                        "link": {
                            "url": link_url
                        }
                    }
                })
            else:
                # 如果URL无效，将其作为普通文本处理
                logger.warning(f"⚠️ 无效URL，作为普通文本处理: [{link_text}]({link_url})")
                rich_text.append({
                    "type": "text",
                    "text": {
                        "content": f"[{link_text}]({link_url})"
                    }
                })
            
            last_end = match.end()
        
        # 添加剩余的普通文本
        if last_end < len(text):
            remaining_text = text[last_end:]
            if remaining_text:
                rich_text.append({
                    "type": "text",
                    "text": {
                        "content": remaining_text
                    }
                })
        
        # 如果没有链接，返回简单文本
        if not rich_text:
            rich_text = [{
                "type": "text",
                "text": {
                    "content": text
                }
            }]
        
        return rich_text
    
    def _create_heading_1_block(self, text: str) -> Dict[str, Any]:
        """创建一级标题块"""
        return {
            "type": "heading_1",
            "heading_1": {
                "rich_text": self._parse_rich_text(text)
            }
        }
    
    def _create_heading_2_block(self, text: str) -> Dict[str, Any]:
        """创建二级标题块"""
        return {
            "type": "heading_2",
            "heading_2": {
                "rich_text": self._parse_rich_text(text)
            }
        }
    
    def _create_heading_3_block(self, text: str) -> Dict[str, Any]:
        """创建三级标题块"""
        return {
            "type": "heading_3",
            "heading_3": {
                "rich_text": self._parse_rich_text(text)
            }
        }
    
    def _create_bulleted_list_block(self, text: str) -> Dict[str, Any]:
        """创建无序列表块"""
        return {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": self._parse_rich_text(text)
            }
        }
    
    def _create_numbered_list_block(self, text: str) -> Dict[str, Any]:
        """创建有序列表块"""
        return {
            "type": "numbered_list_item",
            "numbered_list_item": {
                "rich_text": self._parse_rich_text(text)
            }
        }
    
    def _create_quote_block(self, text: str) -> Dict[str, Any]:
        """创建引用块"""
        return {
            "type": "quote",
            "quote": {
                "rich_text": self._parse_rich_text(text)
            }
        }
    
    def _create_image_block_with_upload(self, file_upload_id: str, alt_text: str = "") -> Dict[str, Any]:
        """创建使用file_upload的图片块"""
        block = {
            "object": "block",
            "type": "image",
            "image": {
                "type": "file_upload",
                "file_upload": {
                    "id": file_upload_id
                }
            }
        }
        
        # 只有在有alt_text时才添加caption
        if alt_text:
            block["image"]["caption"] = [
                {
                    "type": "text",
                    "text": {
                        "content": alt_text
                    }
                }
            ]
        
        logger.info(f"创建file_upload图片块: file_upload_id={file_upload_id}, alt_text='{alt_text}'")
        return block
    
    def _create_image_block_external(self, image_url: str, alt_text: str = "") -> Dict[str, Any]:
        """创建使用外部链接的图片块（回退方案）"""
        return {
            "type": "image",
            "image": {
                "type": "external",
                "external": {
                    "url": image_url
                },
                "caption": [
                    {
                        "type": "text",
                        "text": {
                            "content": alt_text
                        }
                    }
                ] if alt_text else []
            }
        } 