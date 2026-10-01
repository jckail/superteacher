import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db as database
from .config import get_settings
from .routers import ai, attendance, gradebook, roster, system
from .seed import seed_demo

logging.basicConfig(level=logging.INFO)


def create_app(session_factory=None, engine=None, seed: bool | None = None) -> FastAPI:
    settings = get_settings()
    session_factory = session_factory or database.SessionLocal
    engine = engine or database.engine

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from . import models  # noqa: F401  (register tables)

        database.Base.metadata.create_all(engine)  # additive only — existing data is never dropped
        if settings.seed_demo_data if seed is None else seed:
            with session_factory() as s:
                seed_demo(s)
        yield

    app = FastAPI(title="Super Teacher", version=settings.version, lifespan=lifespan)
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"]
    )
    for r in (system, roster, gradebook, attendance, ai):
        app.include_router(r.router, prefix="/api")

    dist = Path(settings.static_dir)
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
