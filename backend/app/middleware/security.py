import time
from collections import OrderedDict
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings


class SecurityMiddleware(BaseHTTPMiddleware):
    """Single-process local limiter. Production needs a shared Redis implementation."""

    def __init__(self, app):
        super().__init__(app)
        self.windows = OrderedDict()

    async def dispatch(self, request, call_next):
        request.state.request_id = str(uuid4())
        path = request.url.path
        webhook = path == "/api/v1/payments/stripe/webhook"
        unsafe = request.method not in ("GET", "HEAD", "OPTIONS")
        settings = get_settings()
        if unsafe and not webhook and (request.cookies.get("hl_session") or path.startswith("/api/v1/auth/")):
            if request.headers.get("origin") != settings.frontend_url:
                return self.error(request, 403, "Invalid request origin")
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > 6 * 1024 * 1024):
            return self.error(request, 413, "Request too large")
        ip = request.client.host if request.client else "unknown"
        group = "auth" if path.startswith("/api/v1/auth/") and unsafe else "write" if unsafe else "read"
        key = (ip, group)
        current = time.monotonic()
        start, count = self.windows.get(key, (current, 0))
        if current - start >= 60:
            start, count = current, 0
        limit = {"auth": 20, "write": 90, "read": 240}[group]
        if count >= limit and not webhook:
            response = self.error(request, 429, "Too many requests; retry in one minute")
            response.headers["Retry-After"] = "60"
            return response
        self.windows[key] = (start, count + 1)
        self.windows.move_to_end(key)
        while len(self.windows) > 10000:
            self.windows.popitem(last=False)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    def error(self, request, status, message):
        return JSONResponse(
            {"error": {"message": message, "request_id": request.state.request_id}}, status_code=status
        )
