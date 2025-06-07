import os
import re
import requests
import mimetypes
from typing import Optional, Dict, Any, List
from notion_client import Client
from datetime import datetime
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
    
    def _upload_image_to_notion(self, image_url: str) -> Optional[str]:
        """
        上传图片到Notion并返回Notion文件URL
        
        Args:
            image_url: 图片URL（可以是本地路径或网络URL）
            
        Returns:
            str: Notion文件URL，如果失败返回None
        """
        try:
            # 判断是否为本地文件路径
            if image_url.startswith('/static/') or image_url.startswith('./'):
                # 本地文件路径，需要读取文件
                local_path = image_url
                if image_url.startswith('/static/'):
                    local_path = f"static{image_url[7:]}"  # 移除/static前缀
                elif image_url.startswith('./'):
                    local_path = image_url[2:]  # 移除./前缀
                
                if not os.path.exists(local_path):
                    logger.warning(f"本地图片文件不存在: {local_path}")
                    return None
                
                # 读取本地文件
                with open(local_path, 'rb') as f:
                    file_content = f.read()
                
                # 获取文件类型
                mime_type, _ = mimetypes.guess_type(local_path)
                if not mime_type or not mime_type.startswith('image/'):
                    logger.warning(f"不支持的图片格式: {local_path}")
                    return None
                
                # 上传到Notion
                filename = os.path.basename(local_path)
                
            else:
                # 网络URL，下载后上传
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                
                file_content = response.content
                mime_type = response.headers.get('content-type', 'image/jpeg')
                
                if not mime_type.startswith('image/'):
                    logger.warning(f"URL返回的不是图片: {image_url}")
                    return None
                
                # 从URL提取文件名
                filename = os.path.basename(image_url.split('?')[0]) or 'image.jpg'
            
            # 使用Notion API上传文件
            # 注意：Notion API需要先创建页面，然后上传文件到页面
            # 这里我们返回一个临时的标记，在实际创建页面时再处理
            return f"NOTION_UPLOAD:{image_url}"
            
        except Exception as e:
            logger.error(f"上传图片到Notion失败: {e}")
            return None
    
    def _process_images_in_markdown(self, markdown: str) -> str:
        """
        处理Markdown中的图片，上传到Notion并替换链接
        
        Args:
            markdown: 原始Markdown内容
            
        Returns:
            str: 处理后的Markdown内容
        """
        # 匹配Markdown图片语法 ![alt](url)
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        
        def replace_image(match):
            alt_text = match.group(1)
            image_url = match.group(2)
            
            # 上传图片到Notion
            notion_url = self._upload_image_to_notion(image_url)
            if notion_url:
                return f"![{alt_text}]({notion_url})"
            else:
                # 如果上传失败，保持原有链接
                logger.warning(f"图片上传失败，保持原链接: {image_url}")
                return match.group(0)
        
        return re.sub(image_pattern, replace_image, markdown)

    def _markdown_to_notion_blocks(self, markdown: str) -> List[Dict[str, Any]]:
        """
        将Markdown内容转换为Notion块格式
        
        Args:
            markdown: Markdown内容
            
        Returns:
            List[Dict]: Notion块列表
        """
        # 首先处理图片上传
        processed_markdown = self._process_images_in_markdown(markdown)
        
        blocks = []
        lines = processed_markdown.split('\n')
        current_paragraph = []
        
        for line in lines:
            line = line.strip()
            
            # 空行处理
            if not line:
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                continue
            
            # 图片处理
            image_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line)
            if image_match:
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                alt_text = image_match.group(1)
                image_url = image_match.group(2)
                blocks.append(self._create_image_block(image_url, alt_text))
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
        """创建段落块"""
        return {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": text
                        }
                    }
                ]
            }
        }
    
    def _create_heading_1_block(self, text: str) -> Dict[str, Any]:
        """创建一级标题块"""
        return {
            "type": "heading_1",
            "heading_1": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": text
                        }
                    }
                ]
            }
        }
    
    def _create_heading_2_block(self, text: str) -> Dict[str, Any]:
        """创建二级标题块"""
        return {
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": text
                        }
                    }
                ]
            }
        }
    
    def _create_heading_3_block(self, text: str) -> Dict[str, Any]:
        """创建三级标题块"""
        return {
            "type": "heading_3",
            "heading_3": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": text
                        }
                    }
                ]
            }
        }
    
    def _create_bulleted_list_block(self, text: str) -> Dict[str, Any]:
        """创建无序列表块"""
        return {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": text
                        }
                    }
                ]
            }
        }
    
    def _create_numbered_list_block(self, text: str) -> Dict[str, Any]:
        """创建有序列表块"""
        return {
            "type": "numbered_list_item",
            "numbered_list_item": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": text
                        }
                    }
                ]
            }
        }
    
    def _create_quote_block(self, text: str) -> Dict[str, Any]:
        """创建引用块"""
        return {
            "type": "quote",
            "quote": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": text
                        }
                    }
                ]
            }
        }
    
    def _create_image_block(self, image_url: str, alt_text: str = "") -> Dict[str, Any]:
        """创建图片块"""
        # 如果是我们标记的需要上传的图片
        if image_url.startswith("NOTION_UPLOAD:"):
            original_url = image_url[14:]  # 移除NOTION_UPLOAD:前缀
            
            # 对于本地文件，使用external类型但提供完整的URL
            if original_url.startswith('/static/'):
                # 构建完整的服务器URL
                base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')
                full_url = f"{base_url}{original_url}"
            else:
                full_url = original_url
            
            return {
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {
                        "url": full_url
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
        else:
            # 普通的外部图片URL
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