"""
SUSE Data Masking Service - Main Application
FastAPI backend with 16-thread concurrent processing
"""
from fastapi import FastAPI, Request
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

# Include routers FIRST (before catch-all)
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


# Serve frontend static files
if os.path.exists(FRONTEND_DIR):
    # Mount assets directory
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")


# Catch-all route for SPA - must be defined AFTER all other routes
@app.api_route("/{full_path:path}", methods=["GET"], include_in_schema=False)
async def serve_spa(request: Request, full_path: str):
    """Serve SPA for all other routes (excluding /api/*)"""
    # Skip API routes
    if full_path.startswith("api/"):
        return {"detail": "Not Found"}
    
    # Check if file exists in frontend dist
    file_path = os.path.join(FRONTEND_DIR, full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Return index.html for SPA routing
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    
    return {"detail": "Not Found"}
