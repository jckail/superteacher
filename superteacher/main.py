import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler  # noqa: F401
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import auth, observability
from . import db as database
from .config import Settings, get_settings
from .routers import ai, attendance, gradebook, reports, roster, system
from .seed import seed_demo

logging.basicConfig(level=logging.INFO)


def _security_headers() -> dict[str, str]:
    csp = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    h = {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cross-Origin-Opener-Policy": "same-origin",
    }
    return h


MAX_BODY_BYTES = 4 * 1024 * 1024  # CSV import is capped at 500k characters (<= ~3 MB once JSON-escaped)


class BodyLimitMiddleware:
    """Reject oversized request bodies before they are buffered (the 401 for anonymous callers comes after parsing)."""

    def __init__(self, app, limit: int = MAX_BODY_BYTES):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.limit:
            return await JSONResponse({"detail": "Request body too large"}, status_code=413)(scope, receive, send)
        seen = 0

        async def limited():
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > self.limit:
                    raise HTTPException(413, "Request body too large")
            return msg

        return await self.app(scope, limited, send)


def create_app(
    session_factory=None, engine=None, seed: bool | None = None, settings: Settings | None = None
) -> FastAPI:
    settings = settings or get_settings()
    session_factory = session_factory or database.SessionLocal
    engine = engine or database.engine

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from . import models  # noqa: F401  (register tables)

        database.run_migrations(engine)  # additive only — existing data is never dropped
        if settings.seed_demo_data if seed is None else seed:
            with session_factory() as s:
                seed_demo(s)
        yield

    secret_dir = None
    if not database.is_memory(engine) and engine.dialect.name == "sqlite" and engine.url.database:
        secret_dir = Path(engine.url.database).resolve().parent
    auth_state = auth.AuthState(settings, secret_dir)

    docs = settings.enable_docs
    app = FastAPI(
        title="Super Teacher",
        version=settings.version,
        lifespan=lifespan,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    app.add_middleware(BodyLimitMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        # Drop "input"/"ctx": echoing the offending value can be huge, deeply nested or un-encodable (-> 500).
        errs = [{"type": e["type"], "loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"detail": errs}, status_code=422)

    app.state.session_factory = session_factory
    app.state.auth = auth_state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Requested-With"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for k, v in _security_headers().items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    # Public: health/version (for probes) and auth. Everything else, including the chat WebSocket, requires a session.
    # (Registered first, so they shadow the identical routes inside routers/system.py, which are auth-protected.)
    @app.get("/api/health", tags=["system"])
    def health(db: Session = Depends(database.get_db)):
        try:
            db.execute(text("SELECT 1"))
            return {"status": "healthy", "database": "ok", "ai": bool(settings.anthropic_api_key)}
        except Exception:
            logging.getLogger(__name__).exception("health check failed")
            return {"status": "unhealthy", "database": "error", "ai": False}

    @app.get("/api/version", tags=["system"])
    def version():
        return {"version": settings.version}

    app.include_router(auth.router, prefix="/api")
    for r in (system, roster, gradebook, attendance, ai, reports):
        app.include_router(r.router, prefix="/api", dependencies=[Depends(auth.require_auth)])

    observability.install(app)  # request ids, access logs, metrics, /api/ready, /api/metrics

    dist = Path(settings.static_dir)
    if (dist / "index.html").is_file():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, "Not Found")  # unknown API routes are JSON 404s, never the SPA shell
            if "\x00" in path:
                raise HTTPException(404, "Not Found")
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
