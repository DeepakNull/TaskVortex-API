import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import trace_id_var

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        token = trace_id_var.set(trace_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            logger.info(
                "Request completed",
                extra={"context": {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": int((time.monotonic() - start) * 1000),
                }},
            )
            return response
        finally:
            trace_id_var.reset(token)