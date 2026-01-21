"""
SUSE Data Masking Service - Main Application
FastAPI backend with 16-thread concurrent processing
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.api import mask, status
from app.core.executor import shutdown_executor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("🦎 SUSE Data Masking Service starting...")
    logger.info("✅ ThreadPoolExecutor initialized with 16 workers")
    yield
    logger.info("🛑 Shutting down...")
    shutdown_executor()
    logger.info("✅ Cleanup completed")


app = FastAPI(
    title="SUSE Data Masking Service",
    description="一站式数据脱敏服务，支持网页上传和 REST API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(mask.router, prefix="/api/v1", tags=["Masking"])
app.include_router(status.router, prefix="/api/v1", tags=["Status"])


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint"""
    return {
        "service": "SUSE Data Masking Service",
        "version": "1.0.0",
        "status": "healthy"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check"""
    from app.core.executor import get_executor_status
    return {
        "status": "healthy",
        "executor": get_executor_status()
    }
