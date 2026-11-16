import json
import logging
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api import admin, agents, auth, dashboard, marketplace, payments, tasks
from app.core.config import get_settings
from app.core.database import get_engine
from app.middleware.security import SecurityMiddleware

settings = get_settings()
logger = logging.getLogger("humanloop")
app = FastAPI(
    title="HumanLoop API",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "X-Filename"],
)
for router in (
    auth.router,
    marketplace.router,
    tasks.router,
    agents.router,
    payments.router,
    dashboard.router,
    admin.router,
):
    app.include_router(router, prefix="/api/v1")


def error(request, status, message):
    return JSONResponse(
        status_code=status,
        content={
            "error": {"message": message, "request_id": getattr(request.state, "request_id", "unknown")}
        },
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error(request, exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not echo rejected password, token, or private message values.
    messages = [".".join(str(part) for part in item["loc"]) + ": " + item["msg"] for item in exc.errors()]
    return error(request, 422, "; ".join(messages))


@app.exception_handler(IntegrityError)
async def conflict(request: Request, exc: IntegrityError):
    return error(request, 409, "Resource conflict; reload and try again")


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    logger.error(
        json.dumps(
            {
                "event": "request_failed",
                "request_id": getattr(request.state, "request_id", None),
                "exception_type": type(exc).__name__,
                # Locations only: never SQL text, parameters, exception messages or frame locals.
                "frames": [
                    {
                        "file": frame.filename.replace("\\", "/").split("/")[-1],
                        "line": frame.lineno,
                        "function": frame.name,
                    }
                    for frame in traceback.extract_tb(exc.__traceback__)[-8:]
                ],
                "sqlstate": getattr(getattr(exc, "orig", None), "sqlstate", None),
            }
        )
    )
    return error(request, 500, "Unexpected server error")


@app.get("/health/live")
async def live():
    return {"status": "ok"}


@app.get("/health/ready")
async def ready():
    async with get_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/api/v1/config")
async def config():
    return {
        "demo_mode": settings.demo_mode,
        "public_bookings_enabled": False,
        "payment_provider": settings.payment_provider,
        "environment": settings.environment,
    }
