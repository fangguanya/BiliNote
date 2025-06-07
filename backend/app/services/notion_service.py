import os
import re
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
            # 准备页面属性
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": note_result.audio_meta.title or "未命名笔记"
                            }
                        }
                    ]
                }
            }
            
            # 添加可选属性
            if hasattr(note_result.audio_meta, 'duration') and note_result.audio_meta.duration:
                properties["时长"] = {
                    "number": note_result.audio_meta.duration
                }
            
            if hasattr(note_result.audio_meta, 'platform') and note_result.audio_meta.platform:
                properties["平台"] = {
                    "select": {
                        "name": note_result.audio_meta.platform
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