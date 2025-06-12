# app/core/exception_handlers.py
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import functools
import traceback
import asyncio

from app.utils.logger import get_logger
from app.utils.response import ResponseWrapper
from app.utils.status_code import StatusCode
logger = get_logger(__name__)

def record_request_error(request_info: dict, error: Exception):
    """记录请求错误信息"""
    logger.error(f"请求处理失败: {error}")
    logger.error(f"请求信息: {request_info}")
    logger.error(traceback.format_exc())

def wrap_request_handler(func):
    """装饰器：包装请求处理函数，统一异常处理"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
        except Exception as e:
            # 记录请求信息
            request_info = {
                "args": args,
                "kwargs": kwargs
            }
            record_request_error(request_info, e)
            # 重新抛出异常，让FastAPI的异常处理器处理
            raise
    return wrapper

def register_exception_handlers(app):
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            loc = err.get("loc", [])
            field = loc[-1] if loc else "body"
            msg = err.get("msg", "参数不合法")
            errors.append({"field": field, "error": msg})
        return JSONResponse(
            status_code=400,
            content=ResponseWrapper.error(msg="参数验证失败", code=StatusCode.PARAM_ERROR, data=errors)
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ResponseWrapper.error(msg=str(exc.detail), code=StatusCode.FAIL)
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"服务器内部错误: {exc}")
        return JSONResponse(
            status_code=500,
            content=ResponseWrapper.error(msg="服务器内部错误", code=StatusCode.FAIL, data=str(exc))
        )
