"""
SUSE Data Masking Service - Main Application
FastAPI backend with 16-thread concurrent processing
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import asyncio
import logging
import os

from app.api import mask, status, rules
from app.core.executor import shutdown_executor
from app.core.auth import APIKeyMiddleware, AUTH_ENABLED
from app.core.session import cleanup_expired_sessions
from app.engine.rule_service import rule_service

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
    logger.info(f"🔐 API Key Authentication: {'ENABLED' if AUTH_ENABLED else 'DISABLED (dev mode)'}")
    # Initialize rules DB + cache
    rule_service.initialize()
    logger.info("✅ Rules engine initialized (SQLite + in-memory cache)")

    # Start periodic session cleanup task
    async def _session_cleanup_loop():
        while True:
            await asyncio.sleep(600)  # Every 10 minutes
            try:
                cleanup_expired_sessions()
            except Exception:
                logger.warning("Session cleanup failed", exc_info=True)

    cleanup_task = asyncio.create_task(_session_cleanup_loop())

    yield

    cleanup_task.cancel()
    logger.info("🛑 Shutting down...")
    shutdown_executor()
    logger.info("✅ Cleanup completed")


app = FastAPI(
    title="Data Masking API",
    description="Mask sensitive data in text files and archives",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "Masking", "description": "File upload and masking"},
        {"name": "Status", "description": "Service status"},
    ]
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key authentication middleware
app.add_middleware(APIKeyMiddleware)

# Include routers FIRST (before catch-all)
# Rules router FIRST — so /rules, /rules/suggestions, /rules/changelog
# take precedence over mask.py's catch-all endpoints
app.include_router(rules.router, prefix="/api/v1", tags=["Rules"])
app.include_router(mask.router, prefix="/api/v1", tags=["Masking"])
app.include_router(status.router, prefix="/api/v1", tags=["Status"])


# Serve frontend static files
if os.path.exists(FRONTEND_DIR):
    # Mount assets directory
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")


# Health check endpoint for Docker healthcheck
@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


# Catch-all route for SPA - must be defined AFTER all other routes
@app.api_route("/{full_path:path}", methods=["GET"], include_in_schema=False)
async def serve_spa(request: Request, full_path: str):
    """Serve SPA for all other routes (excluding /api/*)"""
    # Skip API routes
    if full_path.startswith("api/"):
        return {"detail": "Not Found"}
    
    # Check if file exists in frontend dist
    file_path = os.path.join(FRONTEND_DIR, full_path)
    # Prevent path traversal — resolved path must stay within FRONTEND_DIR
    real_path = os.path.realpath(file_path)
    real_frontend = os.path.realpath(FRONTEND_DIR)
    if os.path.isfile(real_path) and real_path.startswith(real_frontend + os.sep):
        return FileResponse(real_path)
    
    # Return index.html for SPA routing
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    
    return {"detail": "Not Found"}
