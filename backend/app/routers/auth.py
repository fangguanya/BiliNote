"""
认证相关路由
支持bilibili和douyin的二维码登录
"""

import asyncio
import json
import time
import uuid
from typing import Dict, Optional
import re

import httpx
import qrcode
from fastapi import APIRouter, HTTPException, BackgroundTasks
from io import BytesIO
import base64
from pydantic import BaseModel

from app.services.cookie_manager import CookieConfigManager
from app.utils.response import ResponseWrapper as R
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# 存储登录状态的临时缓存
login_sessions: Dict[str, Dict] = {}

cookie_manager = CookieConfigManager()


class LoginRequest(BaseModel):
    platform: str  # bilibili, douyin, kuaishou, baidu_pan


class LoginStatusResponse(BaseModel):
    status: str  # pending, success, failed, expired
    message: str
    cookie: Optional[str] = None


@router.post("/auth/generate_qr")
async def generate_qr_code(request: LoginRequest):
    """生成登录二维码"""
    try:
        platform = request.platform.lower()
        
        if platform == "bilibili":
            return await generate_bilibili_qr()
        elif platform == "douyin":
            return await generate_douyin_qr()
        elif platform == "kuaishou":
            return await generate_kuaishou_qr()
        elif platform == "baidu_pan":
            return await generate_baidu_pan_qr()
        else:
            raise HTTPException(status_code=400, detail="不支持的平台")
            
    except Exception as e:
        logger.error(f"❌ 生成二维码失败: {e}")
        return R.error(f"生成二维码失败: {str(e)}")


@router.get("/auth/login_status/{session_id}")
async def check_login_status(session_id: str):
    """检查登录状态"""
    try:
        if session_id not in login_sessions:
            return R.error("登录会话不存在", code=404)
        
        session = login_sessions[session_id]
        platform = session.get("platform")
        
        # 检查会话是否过期（15分钟）
        if time.time() - session.get("created_at", 0) > 900:
            del login_sessions[session_id]
            return R.success({
                "status": "expired",
                "message": "二维码已过期，请重新生成"
            })
        
        if platform == "bilibili":
            return await check_bilibili_login_status(session_id)
        elif platform == "douyin":
            return await check_douyin_login_status(session_id)
        elif platform == "kuaishou":
            return await check_kuaishou_login_status(session_id)
        elif platform == "baidu_pan":
            return await check_baidu_pan_login_status(session_id)
        else:
            return R.error("不支持的平台")
            
    except Exception as e:
        logger.error(f"❌ 检查登录状态失败: {e}")
        return R.error(f"检查登录状态失败: {str(e)}")


async def generate_bilibili_qr():
    """生成B站登录二维码"""
    logger.info("🔧 生成B站登录二维码")
    
    try:
        # 获取二维码生成URL
        async with httpx.AsyncClient() as client:
            # 获取二维码URL
            qr_url_response = await client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
            )
            
            qr_data = qr_url_response.json()
            
            if qr_data.get("code") != 0:
                raise HTTPException(status_code=500, detail="获取B站二维码失败")
            
            qr_url = qr_data["data"]["url"]
            qrcode_key = qr_data["data"]["qrcode_key"]
            
            # 生成二维码图片
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # 转换为base64
            img_buffer = BytesIO()
            qr_img.save(img_buffer, format='PNG')
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
            
            # 创建登录会话
            session_id = str(uuid.uuid4())
            login_sessions[session_id] = {
                "platform": "bilibili",
                "qrcode_key": qrcode_key,
                "created_at": time.time(),
                "status": "pending"
            }
            
            logger.info(f"✅ B站二维码生成成功: {session_id}")
            
            return R.success({
                "session_id": session_id,
                "qr_code": f"data:image/png;base64,{img_base64}",
                "expires_in": 900,  # 15分钟
                "message": "请使用哔哩哔哩APP扫描二维码登录"
            })
            
    except Exception as e:
        logger.error(f"❌ 生成B站二维码失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成B站二维码失败: {str(e)}")


async def generate_douyin_qr():
    """生成抖音登录二维码"""
    logger.info("🔧 生成抖音登录二维码")
    
    try:
        # 抖音登录二维码API
        async with httpx.AsyncClient() as client:
            # 获取抖音登录二维码
            qr_response = await client.get(
                "https://sso.douyin.com/get_qrcode/",
                params={
                    "next": "https://www.douyin.com/",
                    "aid": "6383",
                    "service": "https://www.douyin.com",
                    "language": "zh"
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Referer": "https://www.douyin.com/"
                }
            )
            
            qr_data = qr_response.json()
            
            if qr_data.get("error_code") != 0:
                raise HTTPException(status_code=500, detail="获取抖音二维码失败")
            
            # 获取二维码信息
            qr_info = qr_data.get("data", {})
            token = qr_info.get("token")
            qr_code_base64 = qr_info.get("qrcode")
            
            if not token or not qr_code_base64:
                raise HTTPException(status_code=500, detail="抖音二维码数据不完整")
            
            # 创建登录会话
            session_id = str(uuid.uuid4())
            login_sessions[session_id] = {
                "platform": "douyin",
                "token": token,
                "created_at": time.time(),
                "status": "pending"
            }
            
            logger.info(f"✅ 抖音二维码生成成功: {session_id}")
            
            return R.success({
                "session_id": session_id,
                "qr_code": f"data:image/png;base64,{qr_code_base64}",
                "expires_in": 900,  # 15分钟
                "message": "请使用抖音APP扫描二维码登录"
            })
            
    except Exception as e:
        logger.error(f"❌ 生成抖音二维码失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成抖音二维码失败: {str(e)}")


async def generate_kuaishou_qr():
    """生成快手登录二维码"""
    logger.info("🔧 生成快手登录二维码")
    
    try:
        # 快手登录二维码API
        async with httpx.AsyncClient() as client:
            # 获取快手登录二维码
            qr_response = await client.get(
                "https://passport.kuaishou.com/passport/qrcode/generate",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
            )
            
            qr_data = qr_response.json()
            
            if qr_data.get("code") != 0:
                raise HTTPException(status_code=500, detail="获取快手二维码失败")
            
            # 获取二维码信息
            qr_info = qr_data.get("data", {})
            qr_id = qr_info.get("qr_id")
            qr_url = qr_info.get("qrcode_index_url")
            
            # 生成二维码图片
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # 转换为base64
            img_buffer = BytesIO()
            qr_img.save(img_buffer, format='PNG')
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
            
            # 创建登录会话
            session_id = str(uuid.uuid4())
            login_sessions[session_id] = {
                "platform": "kuaishou",
                "qr_id": qr_id,
                "created_at": time.time(),
                "status": "pending"
            }
            
            logger.info(f"✅ 快手二维码生成成功: {session_id}")
            
            return R.success({
                "session_id": session_id,
                "qr_code": f"data:image/png;base64,{img_base64}",
                "expires_in": 900,  # 15分钟
                "message": "请使用快手APP扫描二维码登录"
            })
            
    except Exception as e:
        logger.error(f"❌ 生成快手二维码失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成快手二维码失败: {str(e)}")


async def generate_baidu_pan_qr():
    """生成百度网盘登录二维码"""
    logger.info("🔧 生成百度网盘登录二维码")
    
    try:
        # 百度网盘登录二维码API
        async with httpx.AsyncClient() as client:
            # 第一步：获取二维码生成参数
            gid = str(uuid.uuid4()).replace('-', '').upper()
            
            # 获取百度登录二维码 - 更新为最新的API
            qr_response = await client.get(
                "https://passport.baidu.com/v2/api/getqrcode",
                params={
                    "gid": gid,
                    "callback": "bd__cbs__qrcode",
                    "lp": "pc",
                    "qrloginfrom": "pc",
                    "_": int(time.time() * 1000)
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://pan.baidu.com/",
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Sec-Fetch-Dest": "script",
                    "Sec-Fetch-Mode": "no-cors",
                    "Sec-Fetch-Site": "cross-site"
                }
            )
            
            qr_text = qr_response.text
            logger.info(f"🔍 百度API响应: {qr_text[:200]}...")
            
            # 解析JSONP响应
            try:
                # 查找JSON数据的开始和结束位置
                start_pos = qr_text.find('(')
                end_pos = qr_text.rfind(')')
                
                if start_pos == -1 or end_pos == -1:
                    logger.warning("⚠️ 响应不是JSONP格式，尝试直接解析JSON")
                    qr_data = qr_response.json()
                else:
                    json_str = qr_text[start_pos + 1:end_pos]
                    qr_data = json.loads(json_str)
                    
            except Exception as parse_error:
                logger.error(f"❌ 解析响应失败: {parse_error}, 原始响应: {qr_text[:500]}")
                raise HTTPException(status_code=500, detail="解析百度API响应失败")
            
            logger.info(f"📋 解析后的数据: {qr_data}")
            
            # 检查响应状态
            errno = qr_data.get("errno")
            if errno is not None and str(errno) != "0":
                error_msg = qr_data.get("msg", "未知错误")
                logger.error(f"❌ 百度API返回错误: errno={errno}, msg={error_msg}")
                raise HTTPException(status_code=500, detail=f"百度API错误: {error_msg}")
            
            # 获取二维码信息 - 修复：百度API直接返回二维码图片URL
            # 检查是否有data字段（新API格式）
            if "data" in qr_data:
                qr_info = qr_data["data"]
                qr_img_url = qr_info.get("qrurl")
                sign = qr_info.get("sign")
            else:
                # 旧API格式，直接从根部获取数据
                imgurl = qr_data.get("imgurl")
                sign = qr_data.get("sign")
                
                if imgurl:
                    # 构造完整的二维码图片URL
                    if not imgurl.startswith("http"):
                        qr_img_url = f"https://{imgurl}"
                    else:
                        qr_img_url = imgurl
                else:
                    qr_img_url = None
            
            logger.info(f"🖼️ 二维码图片URL: {qr_img_url}")
            logger.info(f"🔑 签名: {sign}")
            
            if not qr_img_url or not sign:
                logger.error(f"❌ 二维码数据不完整: qr_img_url={qr_img_url}, sign={sign}")
                raise HTTPException(status_code=500, detail="百度二维码数据不完整")
            
            # 下载百度提供的二维码图片并转换为base64
            try:
                async with httpx.AsyncClient() as img_client:
                    img_response = await img_client.get(qr_img_url, timeout=10)
                    img_response.raise_for_status()
                    
                    # 直接使用百度返回的二维码图片
                    qr_code_base64 = base64.b64encode(img_response.content).decode()
                    
                    logger.info("✅ 成功获取百度二维码图片")
                    
            except Exception as img_error:
                logger.error(f"❌ 获取百度二维码图片失败: {img_error}")
                # 如果获取图片失败，直接返回图片URL让前端处理
                qr_code_base64 = None
            
            # 创建登录会话
            session_id = str(uuid.uuid4())
            login_sessions[session_id] = {
                "platform": "baidu_pan",
                "created_at": time.time(),
                "status": "pending",
                "sign": sign,
                "gid": gid
            }
            
            logger.info(f"✅ 百度网盘二维码生成成功: {session_id}")
            
            # 构建响应数据
            response_data = {
                "session_id": session_id,
                "expires_in": 300,  # 5分钟，增加有效期
                "message": "请使用百度APP扫描二维码登录"
            }
            
            # 如果成功获取到base64图片数据，使用base64格式
            if qr_code_base64:
                response_data["qr_code"] = f"data:image/png;base64,{qr_code_base64}"
            else:
                # 否则直接返回百度的图片URL，让前端直接显示
                response_data["qr_code"] = qr_img_url
                response_data["qr_image_url"] = qr_img_url
                logger.info(f"📋 返回百度原始二维码URL: {qr_img_url}")
            
            return R.success(response_data)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 生成百度网盘二维码失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成百度网盘二维码失败: {str(e)}")


async def check_bilibili_login_status(session_id: str):
    """检查B站登录状态"""
    session = login_sessions[session_id]
    qrcode_key = session["qrcode_key"]
    
    try:
        async with httpx.AsyncClient() as client:
            # 检查登录状态
            check_response = await client.get(
                f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={qrcode_key}",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
            )
            
            check_data = check_response.json()
            
            if check_data.get("code") != 0:
                return R.success({
                    "status": "pending",
                    "message": "等待扫码..."
                })
            
            status_code = check_data["data"]["code"]
            
            if status_code == 86101:
                # 未扫码
                return R.success({
                    "status": "pending",
                    "message": "等待扫码..."
                })
            elif status_code == 86090:
                # 已扫码未确认
                return R.success({
                    "status": "pending",
                    "message": "已扫码，请在手机上确认登录"
                })
            elif status_code == 0:
                # 登录成功
                # 提取cookie
                cookies = check_response.headers.get('set-cookie', '')
                
                # 保存cookie
                cookie_manager.set("bilibili", cookies)
                
                # 更新会话状态
                session["status"] = "success"
                session["cookie"] = cookies
                
                logger.info(f"✅ B站登录成功: {session_id}")
                
                return R.success({
                    "status": "success",
                    "message": "登录成功！",
                    "cookie": cookies
                })
            else:
                # 其他错误
                return R.success({
                    "status": "failed",
                    "message": f"登录失败: {check_data.get('message', '未知错误')}"
                })
                
    except Exception as e:
        logger.error(f"❌ 检查B站登录状态失败: {e}")
        return R.error(f"检查登录状态失败: {str(e)}")


async def check_douyin_login_status(session_id: str):
    """检查抖音登录状态"""
    session = login_sessions[session_id]
    token = session["token"]
    
    try:
        async with httpx.AsyncClient() as client:
            # 检查抖音登录状态
            check_response = await client.get(
                "https://sso.douyin.com/check_qrconnect/",
                params={
                    "next": "https://www.douyin.com/",
                    "token": token,
                    "service": "https://www.douyin.com",
                    "aid": "6383"
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Referer": "https://www.douyin.com/"
                }
            )
            
            check_data = check_response.json()
            
            if check_data.get("error_code") == 0:
                status = check_data.get("data", {}).get("status")
                
                if status == "3":
                    # 登录成功，获取cookie
                    redirect_url = check_data.get("data", {}).get("redirect_url")
                    
                    if redirect_url:
                        # 访问重定向URL获取cookie
                        cookie_response = await client.get(
                            redirect_url,
                            headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                            },
                            follow_redirects=True
                        )
                        
                        # 提取cookie
                        cookies_dict = cookie_response.cookies
                        cookie_string = "; ".join([f"{name}={value}" for name, value in cookies_dict.items()])
                        
                        # 保存cookie
                        cookie_manager.set("douyin", cookie_string)
                        
                        # 更新会话状态
                        session["status"] = "success"
                        session["cookie"] = cookie_string
                        
                        logger.info(f"✅ 抖音登录成功: {session_id}")
                        
                        return R.success({
                            "status": "success",
                            "message": "登录成功！",
                            "cookie": cookie_string
                        })
                    else:
                        return R.success({
                            "status": "failed",
                            "message": "获取登录信息失败"
                        })
                elif status == "1":
                    return R.success({
                        "status": "pending",
                        "message": "等待扫码..."
                    })
                elif status == "2":
                    return R.success({
                        "status": "pending",
                        "message": "已扫码，请在手机上确认登录"
                    })
                else:
                    return R.success({
                        "status": "failed", 
                        "message": "登录失败"
                    })
            else:
                return R.success({
                    "status": "pending",
                    "message": "等待扫码..."
                })
            
    except Exception as e:
        logger.error(f"❌ 检查抖音登录状态失败: {e}")
        return R.error(f"检查登录状态失败: {str(e)}")


async def check_kuaishou_login_status(session_id: str):
    """检查快手登录状态"""
    session = login_sessions[session_id]
    qr_id = session["qr_id"]
    
    try:
        async with httpx.AsyncClient() as client:
            # 检查快手登录状态 - 使用实际的快手API
            check_response = await client.get(
                "https://id.kuaishou.com/rest/infra/sts",
                params={
                    "kpn": "KUAISHOU_VISION",
                    "captchaToken": qr_id
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Referer": "https://www.kuaishou.com/"
                }
            )
            
            check_data = check_response.json()
            
            # 快手登录状态检查逻辑（需要根据实际API调整）
            if check_data.get("result") == 1:
                # 登录成功
                cookies_dict = check_response.cookies
                cookie_string = "; ".join([f"{name}={value}" for name, value in cookies_dict.items()])
                
                # 保存cookie
                cookie_manager.set("kuaishou", cookie_string)
                
                # 更新会话状态
                session["status"] = "success"
                session["cookie"] = cookie_string
                
                logger.info(f"✅ 快手登录成功: {session_id}")
                
                return R.success({
                    "status": "success",
                    "message": "登录成功！",
                    "cookie": cookie_string
                })
            elif check_data.get("result") == 2:
                return R.success({
                    "status": "pending",
                    "message": "已扫码，请在手机上确认登录"
                })
            elif check_data.get("result") == 0:
                return R.success({
                    "status": "pending",
                    "message": "等待扫码..."
                })
            else:
                return R.success({
                    "status": "failed", 
                    "message": "登录失败"
                })
            
    except Exception as e:
        logger.error(f"❌ 检查快手登录状态失败: {e}")
        return R.error(f"检查登录状态失败: {str(e)}")


async def check_baidu_pan_login_status(session_id: str):
    """检查百度网盘登录状态"""
    session = login_sessions[session_id]
    sign = session.get("sign")
    gid = session.get("gid")
    
    if not sign:
        logger.error(f"❌ 会话缺少sign参数: {session_id}")
        return R.error("会话数据不完整")
    
    try:
        async with httpx.AsyncClient() as client:
            # 检查百度登录状态 - 使用更新的API
            check_response = await client.get(
                "https://passport.baidu.com/channel/unicast",
                params={
                    "channel_id": sign,
                    "callback": "bd__cbs__unicast",
                    "tpl": "netdisk",
                    "apiver": "v3",
                    "_": int(time.time() * 1000)
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://pan.baidu.com/",
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive"
                }
            )
            
            check_text = check_response.text
            logger.info(f"🔍 百度登录状态检查响应: {check_text[:200]}...")
            
            # 解析JSONP响应
            try:
                start_pos = check_text.find('(')
                end_pos = check_text.rfind(')')
                
                if start_pos == -1 or end_pos == -1:
                    logger.warning("⚠️ 状态检查响应不是JSONP格式")
                    return R.success({
                        "status": "pending",
                        "message": "等待扫码..."
                    })
                
                json_str = check_text[start_pos + 1:end_pos]
                check_data = json.loads(json_str)
                
            except Exception as parse_error:
                logger.warning(f"⚠️ 解析状态检查响应失败: {parse_error}")
                return R.success({
                    "status": "pending",
                    "message": "等待扫码..."
                })
            
            logger.info(f"📋 状态检查数据: {check_data}")
            
            # 检查错误状态
            errno = check_data.get("errno")
            if errno is not None and str(errno) != "0":
                error_msg = check_data.get("errmsg", "")
                if "expired" in error_msg.lower() or "timeout" in error_msg.lower():
                    return R.success({
                        "status": "expired",
                        "message": "二维码已过期，请重新生成"
                    })
                else:
                    return R.success({
                        "status": "pending",
                        "message": "等待扫码..."
                    })
            
            # 获取登录状态 - 修复：channel_v直接在根部，不在data字段中
            channel_v = check_data.get("channel_v")
            
            if not channel_v:
                return R.success({
                    "status": "pending", 
                    "message": "等待扫码..."
                })
            
            logger.info(f"🔑 获取到channel_v: {channel_v}")
            
            # 解析channel_v（它是一个JSON字符串）
            login_token = None
            try:
                if isinstance(channel_v, str):
                    channel_v_data = json.loads(channel_v)
                    status = channel_v_data.get("status")
                    v_token = channel_v_data.get("v")
                    logger.info(f"📋 解析channel_v状态: status={status}, v={v_token}")
                    
                    # 百度登录状态说明：
                    # status=1: 用户已扫码，等待确认
                    # status=0且有v字段: 用户已确认登录，v是登录凭证
                    if status == 1:
                        return R.success({
                            "status": "pending",
                            "message": "已扫码，请在手机上确认登录"
                        })
                    elif status == 0 and v_token:
                        login_token = v_token
                        logger.info(f"✅ 用户已确认登录，获取登录凭证: {login_token}")
                    else:
                        return R.success({
                            "status": "pending",
                            "message": "等待扫码..."
                        })
                else:
                    # 如果不是字符串，直接使用原始值作为登录凭证
                    login_token = channel_v
                    logger.info(f"🔍 channel_v不是字符串格式，直接使用: {type(channel_v)}")
                    
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ 解析channel_v JSON失败: {e}, 原始内容: {channel_v}")
                # 如果解析失败，使用原始值作为登录凭证
                login_token = channel_v
            
            # 如果没有获取到登录凭证，继续等待
            if not login_token:
                return R.success({
                    "status": "pending",
                    "message": "等待登录确认..."
                })
            
            # 获取登录信息 - 获取最终的cookie，立即处理避免过期
            logger.info(f"⏰ 立即获取最终登录信息，当前时间: {int(time.time())}")
            
            login_response = await client.get(
                "https://passport.baidu.com/v3/login/main/qrbdusslogin",
                params={
                    "v": login_token,  # 使用解析出的登录凭证
                    "tpl": "netdisk",
                    "u": "https://pan.baidu.com/",
                    "loginVersion": "v4",
                    "qrcode": "1",
                    "apiver": "v3",
                    "tt": int(time.time()),
                    "traceid": "",
                    "callback": "bd__cbs__login"
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://pan.baidu.com/"
                },
                follow_redirects=False,  # 修复：httpx使用follow_redirects而不是allow_redirects
                timeout=30  # 增加超时时间
            )
            
            logger.info(f"🔍 登录响应状态码: {login_response.status_code}")
            logger.info(f"🔍 登录响应头: {login_response.headers}")
            
            # 提取cookie - 修复httpx cookies处理
            cookies_dict = {}
            
            # 方法1：从响应头中提取cookie
            set_cookie_headers = login_response.headers.get_list('set-cookie')
            if set_cookie_headers:
                for cookie_header in set_cookie_headers:
                    # 解析 set-cookie 头，格式如: "BAIDUID=xxx; path=/; domain=.baidu.com"
                    cookie_parts = cookie_header.split(';')
                    if cookie_parts:
                        name_value = cookie_parts[0].strip()
                        if '=' in name_value:
                            name, value = name_value.split('=', 1)
                            cookies_dict[name.strip()] = value.strip()
                            logger.info(f"🍪 提取cookie: {name.strip()}={value.strip()[:20]}...")
            
            # 方法2：从httpx cookies对象提取（备用）
            try:
                for cookie_name, cookie_value in login_response.cookies.items():
                    if cookie_name not in cookies_dict:
                        cookies_dict[cookie_name] = cookie_value
                        logger.info(f"🍪 补充cookie: {cookie_name}={cookie_value[:20]}...")
            except Exception as e:
                logger.warning(f"⚠️ 从cookies对象提取失败: {e}")
            
            # 检查响应内容（可能包含跳转信息）
            login_text = login_response.text
            logger.info(f"🔍 登录响应内容: {login_text[:300]}...")
            
            # 检查是否有过期错误
            if "310005" in login_text or "验证信息已过期" in login_text:
                logger.warning(f"⚠️ 检测到验证信息过期错误，可能需要重新扫码")
                return R.success({
                    "status": "expired",
                    "message": "登录验证已过期，请重新扫码"
                })
            
            # 构建cookie字符串
            cookie_string = "; ".join([f"{name}={value}" for name, value in cookies_dict.items()])
            
            # 检查关键cookie
            has_bduss = "BDUSS" in cookies_dict or "BDUSS" in login_text
            has_stoken = "STOKEN" in cookies_dict or "STOKEN" in login_text
            
            logger.info(f"🍪 Cookie检查: BDUSS={has_bduss}, STOKEN={has_stoken}")
            logger.info(f"🍪 提取的cookies: {list(cookies_dict.keys())}")
            
            if has_bduss or has_stoken or len(cookies_dict) > 0:
                # 尝试从响应文本中提取更多cookie信息
                if "BDUSS" in login_text:
                    # 从响应中提取BDUSS
                    bduss_match = re.search(r'"BDUSS":"([^"]+)"', login_text)
                    if bduss_match:
                        cookies_dict["BDUSS"] = bduss_match.group(1)
                        logger.info("✅ 从响应文本中提取到BDUSS")
                
                if "STOKEN" in login_text:
                    # 从响应中提取STOKEN
                    stoken_match = re.search(r'"STOKEN":"([^"]+)"', login_text)
                    if stoken_match:
                        cookies_dict["STOKEN"] = stoken_match.group(1)
                        logger.info("✅ 从响应文本中提取到STOKEN")
                
                # 重新构建cookie字符串
                cookie_string = "; ".join([f"{name}={value}" for name, value in cookies_dict.items()])
                
                # 保存cookie
                logger.info(f"💾 准备保存百度网盘cookie")
                logger.debug(f"🔍 Cookie字符串长度: {len(cookie_string)}")
                logger.debug(f"🔍 Cookie内容详情: {cookie_string}")
                
                cookie_manager.set("baidu_pan", cookie_string)
                
                # 验证保存是否成功
                saved_cookie = cookie_manager.get("baidu_pan")
                if saved_cookie:
                    logger.info("✅ Cookie保存验证成功")
                    logger.debug(f"🔍 已保存的cookie长度: {len(saved_cookie)}")
                    logger.debug(f"🔍 保存的cookie匹配原始: {saved_cookie == cookie_string}")
                else:
                    logger.error("❌ Cookie保存验证失败")
                
                # 更新会话状态
                session["status"] = "success"
                session["cookie"] = cookie_string
                
                logger.info(f"✅ 百度网盘登录成功: {session_id}")
                logger.info(f"🍪 保存的cookie预览: {cookie_string[:100]}...")
                logger.info(f"📊 Cookie统计: 总长度={len(cookie_string)}, 包含{len(cookies_dict)}个字段")
                
                return R.success({
                    "status": "success",
                    "message": "登录成功！",
                    "cookie": cookie_string
                })
            else:
                return R.success({
                    "status": "pending",
                    "message": "等待扫码确认..."
                })
            
    except Exception as e:
        logger.error(f"❌ 检查百度网盘登录状态失败: {e}")
        return R.error(f"检查登录状态失败: {str(e)}")


@router.get("/auth/cookie_status")
async def get_cookie_status():
    """获取当前cookie状态"""
    try:
        all_cookies = cookie_manager.list_all()
        
        status = {}
        for platform, cookie in all_cookies.items():
            status[platform] = {
                "has_cookie": bool(cookie),
                "cookie_preview": cookie[:50] + "..." if len(cookie) > 50 else cookie
            }
        
        return R.success(status)
        
    except Exception as e:
        logger.error(f"❌ 获取cookie状态失败: {e}")
        return R.error(f"获取cookie状态失败: {str(e)}")


@router.delete("/auth/clear_cookie/{platform}")
async def clear_platform_cookie(platform: str):
    """清除指定平台的cookie"""
    try:
        cookie_manager.delete(platform)
        logger.info(f"✅ 已清除{platform}的cookie")
        
        return R.success(f"已清除{platform}的cookie")
        
    except Exception as e:
        logger.error(f"❌ 清除cookie失败: {e}")
        return R.error(f"清除cookie失败: {str(e)}") 