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
            try:
                children = self._markdown_to_notion_blocks(note_result.markdown)
                logger.info(f"📄 成功解析Markdown，生成 {len(children)} 个内容块")
            except Exception as markdown_error:
                logger.error(f"❌ Markdown解析失败: {markdown_error}")
                # 如果Markdown解析失败，创建一个简单的文本块
                children = [{
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{
                            "type": "text",
                            "text": {
                                "content": f"Markdown解析失败，原始内容:\n\n{note_result.markdown[:2000]}{'...' if len(note_result.markdown) > 2000 else ''}"
                            }
                        }]
                    }
                }]
            
            # 分批创建页面和内容
            response = self._create_page_with_batched_children(
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
            try:
                children = self._markdown_to_notion_blocks(note_result.markdown)
                logger.info(f"📄 成功解析Markdown，生成 {len(children)} 个内容块")
            except Exception as markdown_error:
                logger.error(f"❌ Markdown解析失败: {markdown_error}")
                # 如果Markdown解析失败，创建一个简单的文本块
                children = [{
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{
                            "type": "text",
                            "text": {
                                "content": f"Markdown解析失败，原始内容:\n\n{note_result.markdown[:2000]}{'...' if len(note_result.markdown) > 2000 else ''}"
                            }
                        }]
                    }
                }]
            
            # 分批创建页面和内容
            response = self._create_page_with_batched_children(
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
    
    def _create_page_with_batched_children(self, parent: Dict[str, Any], properties: Dict[str, Any], children: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分批创建页面和内容，避免Notion API的100个children限制
        
        Args:
            parent: 父页面信息
            properties: 页面属性
            children: 子内容块列表
            
        Returns:
            Dict: 创建结果
        """
        try:
            # Notion API限制单次请求最多100个children
            max_children_per_request = 95  # 留一些余量
            
            if len(children) <= max_children_per_request:
                # 如果内容不多，直接创建
                response = self.client.pages.create(
                    parent=parent,
                    properties=properties,
                    children=children
                )
                logger.info(f"✅ 直接创建页面，包含 {len(children)} 个内容块")
                return response
            
            # 内容过多，需要分批处理
            logger.info(f"📦 内容块过多 ({len(children)} 个)，将分批上传")
            
            # 第1步：创建页面，只包含前95个内容块
            initial_children = children[:max_children_per_request]
            remaining_children = children[max_children_per_request:]
            
            response = self.client.pages.create(
                parent=parent,
                properties=properties,
                children=initial_children
            )
            
            page_id = response["id"]
            logger.info(f"✅ 成功创建页面 {page_id}，已添加 {len(initial_children)} 个内容块")
            
            # 第2步：分批添加剩余内容
            batch_count = 0
            while remaining_children:
                batch_count += 1
                # 取下一批内容
                current_batch = remaining_children[:max_children_per_request]
                remaining_children = remaining_children[max_children_per_request:]
                
                # 添加到页面
                try:
                    self.client.blocks.children.append(
                        block_id=page_id,
                        children=current_batch
                    )
                    logger.info(f"✅ 批次 {batch_count}：成功添加 {len(current_batch)} 个内容块")
                except Exception as batch_error:
                    logger.error(f"❌ 批次 {batch_count} 添加失败: {batch_error}")
                    # 即使某个批次失败，也继续处理其他批次
                    continue
            
            logger.info(f"🎉 分批上传完成，页面 {page_id} 总共包含 {len(children)} 个内容块")
            return response
            
        except Exception as e:
            logger.error(f"❌ 分批创建页面失败: {e}")
            raise e

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
        # 限制markdown长度，防止处理过大的内容
        max_markdown_length = 1000000
        if len(markdown) > max_markdown_length:
            logger.warning(f"⚠️ Markdown内容过长 ({len(markdown)} 字符)，截断到 {max_markdown_length} 字符")
            markdown = markdown[:max_markdown_length] + "\n\n[内容已截断...]"
        
        blocks = []
        lines = markdown.split('\n')
        current_paragraph = []
        i = 0
        
        # 限制总行数，防止处理过多行
        max_lines = 50000
        if len(lines) > max_lines:
            logger.warning(f"⚠️ Markdown行数过多 ({len(lines)} 行)，截断到 {max_lines} 行")
            lines = lines[:max_lines] + ["", "[内容已截断...]"]
        
        while i < len(lines):
            line = lines[i].strip()
            
            # 空行处理
            if not line:
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                i += 1
                continue
            
            # 处理包含内联图片的行
            # 先提取所有图片，然后处理剩余文本
            image_pattern = r'\*?\s*!\[([^\]]*)\]\(([^)]+)\)\s*\*?'
            images_in_line = list(re.finditer(image_pattern, line))
            
            if images_in_line:
                # 如果有当前段落，先保存
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                # 处理行中的文本和图片
                last_end = 0
                line_parts = []
                
                for image_match in images_in_line:
                    # 添加图片前的文本
                    before_text = line[last_end:image_match.start()].strip()
                    if before_text:
                        line_parts.append(('text', before_text))
                    
                    # 添加图片信息
                    alt_text = image_match.group(1)
                    image_url = image_match.group(2)
                    line_parts.append(('image', alt_text, image_url))
                    
                    last_end = image_match.end()
                
                # 添加图片后的文本
                after_text = line[last_end:].strip()
                if after_text:
                    line_parts.append(('text', after_text))
                
                # 根据解析结果创建块
                for part in line_parts:
                    if part[0] == 'text':
                        text_content = part[1]
                        # 检查是否是标题
                        if text_content.startswith('#'):
                            level = len(text_content) - len(text_content.lstrip('#'))
                            level = min(level, 3)
                            title_text = text_content.lstrip('#').strip()
                            
                            if level == 1:
                                blocks.append(self._create_heading_1_block(title_text))
                            elif level == 2:
                                blocks.append(self._create_heading_2_block(title_text))
                            else:
                                blocks.append(self._create_heading_3_block(title_text))
                        # 检查是否是列表
                        elif text_content.startswith('- ') or text_content.startswith('* '):
                            list_text = text_content[2:].strip()
                            blocks.append(self._create_bulleted_list_block(list_text))
                        elif re.match(r'^\d+\.\s', text_content):
                            list_text = re.sub(r'^\d+\.\s', '', text_content)
                            blocks.append(self._create_numbered_list_block(list_text))
                        # 检查是否是引用
                        elif text_content.startswith('>'):
                            quote_text = text_content[1:].strip()
                            blocks.append(self._create_quote_block(quote_text))
                        else:
                            # 普通段落
                            blocks.append(self._create_paragraph_block(text_content))
                    
                    elif part[0] == 'image':
                        alt_text, image_url = part[1], part[2]
                        logger.info(f"🖼️ 处理内联图片: {image_url}, alt_text: '{alt_text}'")
                        
                        # 上传图片到Notion并创建图片块
                        try:
                            file_upload_id = self.upload_file_to_notion(image_url)
                            if file_upload_id:
                                logger.info(f"✅ 图片上传成功，创建file_upload图片块")
                                try:
                                    image_block = self._create_image_block_with_upload(file_upload_id, alt_text)
                                    blocks.append(image_block)
                                except Exception as block_error:
                                    logger.error(f"❌ 创建图片块失败: {block_error}")
                                    error_text = f"[图片块创建失败: {alt_text or os.path.basename(image_url)}]"
                                    blocks.append(self._create_paragraph_block(error_text))
                            else:
                                # 如果上传失败，创建一个带有错误信息的段落
                                logger.warning(f"⚠️ 图片上传失败，将作为文本段落处理: {image_url}")
                                error_text = f"[图片上传失败: {os.path.basename(image_url)}]"
                                if alt_text:
                                    error_text = f"[图片上传失败: {alt_text} - {os.path.basename(image_url)}]"
                                blocks.append(self._create_paragraph_block(error_text))
                        except Exception as image_error:
                            logger.error(f"❌ 图片处理完全失败: {image_error}")
                            error_text = f"[图片处理失败: {alt_text or os.path.basename(image_url)}]"
                            blocks.append(self._create_paragraph_block(error_text))
                i += 1
                continue
            
            # 如果没有图片，按原有逻辑处理
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
                i += 1
                continue
            
            # 列表处理
            if line.startswith('- ') or line.startswith('* '):
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                list_text = line[2:].strip()
                blocks.append(self._create_bulleted_list_block(list_text))
                i += 1
                continue
            
            # 数字列表处理
            if re.match(r'^\d+\.\s', line):
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                list_text = re.sub(r'^\d+\.\s', '', line)
                blocks.append(self._create_numbered_list_block(list_text))
                i += 1
                continue
            
            # 代码块处理
            if line.startswith('```'):
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                # 解析代码块
                language = line[3:].strip() or 'text'  # 获取语言，默认为text
                code_lines = []
                
                # 查找代码块结束
                j = i + 1
                while j < len(lines):
                    if lines[j].strip() == '```':
                        break
                    code_lines.append(lines[j])
                    j += 1
                
                # 创建代码块
                if code_lines:
                    code_content = '\n'.join(code_lines)
                    blocks.append(self._create_code_block(code_content, language))
                
                # 跳过已处理的行（包括结束的```）
                i = j + 1
                continue
            
            # 表格处理
            if '|' in line and line.count('|') >= 2:
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                # 收集表格行
                table_rows = []
                j = i
                
                while j < len(lines):
                    current_line = lines[j].strip()
                    if '|' in current_line and current_line.count('|') >= 2:
                        # 跳过分隔线（如 |---|---|）
                        if not re.match(r'^\|[\s\-:]+\|$', current_line):
                            table_rows.append(current_line)
                        j += 1
                    else:
                        break
                
                # 创建表格
                if table_rows:
                    blocks.append(self._create_table_block(table_rows))
                
                i = j
                continue
            
            # 引用处理
            if line.startswith('>'):
                if current_paragraph:
                    blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
                    current_paragraph = []
                
                quote_text = line[1:].strip()
                blocks.append(self._create_quote_block(quote_text))
                i += 1
                continue
            
            # 普通段落
            current_paragraph.append(line)
            i += 1
        
        # 处理最后的段落
        if current_paragraph:
            blocks.append(self._create_paragraph_block('\n'.join(current_paragraph)))
        
        # 检查和优化块数量
        if len(blocks) > 300:  # 如果块数过多，进行合并优化
            logger.warning(f"⚠️ 生成的块数过多 ({len(blocks)} 个)，进行合并优化")
            blocks = self._optimize_blocks_count(blocks)
            logger.info(f"📦 优化后的块数: {len(blocks)} 个")
        
        return blocks
    
    def _optimize_blocks_count(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        优化块数量，合并相邻的相同类型段落块
        
        Args:
            blocks: 原始块列表
            
        Returns:
            List[Dict]: 优化后的块列表
        """
        if not blocks:
            return blocks
        
        optimized_blocks = []
        current_paragraph_texts = []
        
        for block in blocks:
            block_type = block.get("type", "")
            
            # 对于段落块，尝试合并
            if block_type == "paragraph":
                # 提取段落文本
                rich_text = block.get("paragraph", {}).get("rich_text", [])
                paragraph_text = ""
                for rt in rich_text:
                    if rt.get("type") == "text":
                        paragraph_text += rt.get("text", {}).get("content", "")
                
                if paragraph_text.strip():
                    current_paragraph_texts.append(paragraph_text)
                    
                # 如果累积的段落过多，先输出一部分
                if len(current_paragraph_texts) >= 5:
                    combined_text = "\n\n".join(current_paragraph_texts)
                    optimized_blocks.append(self._create_paragraph_block(combined_text))
                    current_paragraph_texts = []
            else:
                # 非段落块，先输出累积的段落
                if current_paragraph_texts:
                    combined_text = "\n\n".join(current_paragraph_texts)
                    optimized_blocks.append(self._create_paragraph_block(combined_text))
                    current_paragraph_texts = []
                
                # 保留非段落块
                optimized_blocks.append(block)
        
        # 处理最后剩余的段落
        if current_paragraph_texts:
            combined_text = "\n\n".join(current_paragraph_texts)
            optimized_blocks.append(self._create_paragraph_block(combined_text))
        
        return optimized_blocks
    
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
    
    def _parse_rich_text(self, text: str, depth: int = 0) -> List[Dict[str, Any]]:
        """解析文本中的链接、格式等，返回rich_text数组"""
        # 防止无限递归，限制递归深度
        if depth > 10:
            logger.warning(f"⚠️ 文本解析递归深度超限 (depth={depth})，返回原文本: {text[:50]}...")
            return [{
                "type": "text",
                "text": {
                    "content": text
                }
            }]
        
        rich_text = []
        
        # 定义所有格式的正则表达式（按优先级排序）
        patterns = [
            # LaTeX 数学公式 ($$...$$) - 最高优先级
            ('math', r'\$\$([^$]+?)\$\$'),
            # 内联代码 (`...`) - 高优先级，避免与其他格式冲突
            ('code', r'`([^`]+?)`'),
            # 链接 ([text](url)) - 优先处理，避免与加粗斜体冲突
            ('link', r'\[([^\]]+?)\]\(([^)]+?)\)'),
            # 加粗 (**...** 或 __...__) 
            ('bold_double', r'\*\*([^*]+?)\*\*'),
            ('bold_underscore', r'__([^_]+?)__'),
            # 删除线 (~~...~~)
            ('strikethrough', r'~~([^~]+?)~~'),
            # 斜体 (*...* 或 _..._) - 最后处理，避免与加粗冲突
            ('italic_star', r'\*([^*]+?)\*'),
            ('italic_underscore', r'_([^_]+?)_'),
        ]
        
        # 创建一个包含所有模式的大正则表达式
        combined_patterns = []
        for pattern_name, pattern in patterns:
            if pattern_name == 'link':
                # 链接需要特殊处理，因为它有两个捕获组
                combined_patterns.append(f'(?P<{pattern_name}>{pattern})')
            else:
                combined_patterns.append(f'(?P<{pattern_name}>{pattern})')
        
        combined_regex = '|'.join(combined_patterns)
        
        last_end = 0
        
        for match in re.finditer(combined_regex, text):
            # 添加匹配前的普通文本
            if match.start() > last_end:
                plain_text = text[last_end:match.start()]
                if plain_text:
                    rich_text.extend(self._parse_nested_formats(plain_text, depth + 1))
            
            # 处理匹配的格式
            match_type = match.lastgroup
            
            if match_type == 'math':
                # LaTeX 数学公式 - 重新解析以获取正确内容
                math_match = re.search(r'\$\$([^$]+?)\$\$', match.group(0))
                if math_match:
                    formula = math_match.group(1)
                    rich_text.append({
                        "type": "equation",
                        "equation": {
                            "expression": formula
                        }
                    })
            
            elif match_type == 'code':
                # 内联代码 - 重新解析以获取正确内容
                code_match = re.search(r'`([^`]+?)`', match.group(0))
                if code_match:
                    code_content = code_match.group(1)
                    rich_text.append({
                        "type": "text",
                        "text": {
                            "content": code_content
                        },
                        "annotations": {
                            "code": True
                        }
                    })
            
            elif match_type in ['bold_double', 'bold_underscore']:
                # 加粗文本 - 重新解析以获取正确内容
                if match_type == 'bold_double':
                    bold_match = re.search(r'\*\*([^*]+?)\*\*', match.group(0))
                else:
                    bold_match = re.search(r'__([^_]+?)__', match.group(0))
                
                if bold_match:
                    bold_content = bold_match.group(1)
                    rich_text.append({
                        "type": "text",
                        "text": {
                            "content": bold_content
                        },
                        "annotations": {
                            "bold": True
                        }
                    })
            
            elif match_type in ['italic_star', 'italic_underscore']:
                # 斜体文本 - 重新解析以获取正确内容
                if match_type == 'italic_star':
                    italic_match = re.search(r'\*([^*]+?)\*', match.group(0))
                else:
                    italic_match = re.search(r'_([^_]+?)_', match.group(0))
                
                if italic_match:
                    italic_content = italic_match.group(1)
                    rich_text.append({
                        "type": "text",
                        "text": {
                            "content": italic_content
                        },
                        "annotations": {
                            "italic": True
                        }
                    })
            
            elif match_type == 'strikethrough':
                # 删除线文本 - 重新解析以获取正确内容
                strike_match = re.search(r'~~([^~]+?)~~', match.group(0))
                if strike_match:
                    strike_content = strike_match.group(1)
                    rich_text.append({
                        "type": "text",
                        "text": {
                            "content": strike_content
                        },
                        "annotations": {
                            "strikethrough": True
                        }
                    })
            
            elif match_type == 'link':
                # 链接处理
                # 使用原始匹配重新提取链接内容
                link_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', match.group(0))
                if link_match:
                    link_text = link_match.group(1)
                    link_url = link_match.group(2)
                    
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
                rich_text.extend(self._parse_nested_formats(remaining_text, depth + 1))
        
        # 如果没有任何格式，返回简单文本
        if not rich_text:
            rich_text = [{
                "type": "text",
                "text": {
                    "content": text
                }
            }]
        
        return rich_text
    
    def _parse_nested_formats(self, text: str, depth: int = 0) -> List[Dict[str, Any]]:
        """处理嵌套格式（如同时有加粗和斜体）"""
        # 防止无限递归，限制递归深度
        if depth > 50:
            logger.warning(f"⚠️ 嵌套格式解析递归深度超限 (depth={depth})，返回原文本: {text[:50]}...")
            return [{
                "type": "text",
                "text": {
                    "content": text
                }
            }]
        
        # 简化版本：如果文本中没有特殊格式标记，直接返回普通文本
        # 这里可以进一步扩展来处理更复杂的嵌套格式
        if not any(marker in text for marker in ['**', '__', '*', '_', '`', '$$']):
            return [{
                "type": "text",
                "text": {
                    "content": text
                }
            }]
        
        # 如果有格式标记，递归调用主解析函数
        return self._parse_rich_text(text, depth + 1)
    
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
    
    def _create_code_block(self, code: str, language: str = "text") -> Dict[str, Any]:
        """创建代码块"""
        # 清理语言标识符，只保留Notion支持的语言
        supported_languages = {
            'javascript', 'typescript', 'python', 'java', 'c', 'cpp', 'csharp', 'c#',
            'go', 'rust', 'php', 'ruby', 'swift', 'kotlin', 'scala', 'r', 'matlab',
            'sql', 'html', 'css', 'scss', 'less', 'json', 'xml', 'yaml', 'markdown',
            'bash', 'shell', 'powershell', 'dockerfile', 'makefile', 'text', 'plain'
        }
        
        # 标准化语言名称
        clean_language = language.lower().strip()
        if clean_language in ['js', 'node']:
            clean_language = 'javascript'
        elif clean_language in ['ts']:
            clean_language = 'typescript'
        elif clean_language in ['py']:
            clean_language = 'python'
        elif clean_language in ['sh', 'zsh']:
            clean_language = 'bash'
        elif clean_language in ['yml']:
            clean_language = 'yaml'
        elif clean_language in ['md']:
            clean_language = 'markdown'
        elif clean_language not in supported_languages:
            clean_language = 'text'
        
        return {
            "type": "code",
            "code": {
                "caption": [],
                "rich_text": [{
                    "type": "text",
                    "text": {
                        "content": code
                    }
                }],
                "language": clean_language
            }
        }
    
    def _create_table_block(self, table_rows: List[str]) -> Dict[str, Any]:
        """创建表格块"""
        if not table_rows:
            return self._create_paragraph_block("空表格")
        
        # 解析表格数据
        parsed_rows = []
        for row in table_rows:
            # 移除首尾的|，然后分割
            cells = [cell.strip() for cell in row.strip('|').split('|')]
            parsed_rows.append(cells)
        
        if not parsed_rows:
            return self._create_paragraph_block("表格解析失败")
        
        # 确定表格尺寸
        max_cols = max(len(row) for row in parsed_rows)
        table_width = min(max_cols, 10)  # Notion表格最大10列
        table_height = min(len(parsed_rows), 100)  # 限制表格高度
        
        # 创建表格行
        table_children = []
        for i, row in enumerate(parsed_rows[:table_height]):
            # 确保每行都有足够的列
            padded_row = row + [''] * (table_width - len(row))
            table_row_cells = []
            
            for j, cell_content in enumerate(padded_row[:table_width]):
                cell_rich_text = self._parse_rich_text(cell_content) if cell_content else []
                table_row_cells.append(cell_rich_text)
            
            table_children.append({
                "type": "table_row",
                "table_row": {
                    "cells": table_row_cells
                }
            })
        
        return {
            "type": "table",
            "table": {
                "table_width": table_width,
                "has_column_header": len(parsed_rows) > 1,  # 第一行作为表头
                "has_row_header": False,
                "children": table_children
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