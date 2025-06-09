from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import note, provider, model, config, auth, notion, task
from .utils.response import ResponseWrapper as R


def create_app(lifespan=None) -> FastAPI:
    app = FastAPI(title="BiliNote", lifespan=lifespan)
    
    # 添加CORS中间件 - 临时允许所有来源用于调试
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 临时允许所有来源
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 添加通用health检查端点
    @app.get("/api/health")
    def health_check():
        """应用健康检查"""
        return R.success({
            "service": "BiliNote API",
            "status": "healthy",
            "version": "1.0.0",
            "message": "服务运行正常"
        })
    
    app.include_router(note.router, prefix="/api")
    app.include_router(provider.router, prefix="/api")
    app.include_router(model.router,prefix="/api")
    app.include_router(config.router,  prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(notion.router, prefix="/api/notion")
    app.include_router(task.router, prefix="/api")
    return app
