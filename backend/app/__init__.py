from fastapi import FastAPI
from .routers import note, provider, model, config, auth


def create_app(lifespan=None) -> FastAPI:
    app = FastAPI(title="BiliNote", lifespan=lifespan)
    app.include_router(note.router, prefix="/api")
    app.include_router(provider.router, prefix="/api")
    app.include_router(model.router,prefix="/api")
    app.include_router(config.router,  prefix="/api")
    app.include_router(auth.router, prefix="/api")
    return app
