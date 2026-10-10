from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.rabbitmq import close_rabbitmq, connect_rabbitmq
from app.middlewares.rate_limiter import RateLimiterMiddleware
from .api.health import router as health_router
from .api.v1.tasks import router as tasks_router
from .api.v1.users import router as user_router
from .api.v1.metrics import router as metrics_router
from .models import * 
from app.core.logging import listener, setup_logging
from app.middlewares.logging_middleware import LoggingMiddleware
import logging 

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting application and initializing database...")
    
    await connect_rabbitmq()
    

    try:
        yield
    finally:
        await close_rabbitmq()
        listener.stop()
        logger.info("Application shutting down")
    

app = FastAPI(
    title="TaskVortex API",
    description="Production-grade asynchronous task orchestration engine.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(RateLimiterMiddleware)
app.add_middleware(LoggingMiddleware)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    
    for error in exc.errors():
        errors.append({
            "field": " -> ".join(
                str(loc) for loc in error["loc"] if loc != "body"
            ),
            "issue": error["msg"],
            "rejected_value": error.get("input")
        })
        
    return JSONResponse(
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT,
        content = {
            'success': False, 
            "error_type": "ValidationError",
            "details": errors
        }
    )
    

app.include_router(health_router, prefix='/api')
app.include_router(tasks_router, prefix='/api')
app.include_router(user_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")