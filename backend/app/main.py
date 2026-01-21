"""
SUSE Data Masking Service - Main Application
FastAPI backend with 16-thread concurrent processing
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
import os

from app.api import mask, status
from app.core.executor import shutdown_executor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Frontend dist path
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "../../frontend/dist")


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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(mask.router, prefix="/api/v1", tags=["Masking"])
app.include_router(status.router, prefix="/api/v1", tags=["Status"])


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check"""
    from app.core.executor import get_executor_status
    return {
        "status": "healthy",
        "executor": get_executor_status()
    }


# Mount static files for frontend
if os.path.exists(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA for all other routes"""
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
