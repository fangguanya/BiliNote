"""
认证相关路由
支持bilibili和douyin的二维码登录
"""

import asyncio
import json
import time
import uuid
from typing import Dict, Optional

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
    platform: str  # bilibili, douyin, kuaishou


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