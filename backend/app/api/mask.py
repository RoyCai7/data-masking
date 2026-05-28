"""
Masking API endpoints
Handles file upload, processing, and download
Supports archive files (tgz, tar.gz, zip, etc.)
"""
import uuid
import time
import asyncio
import os
import tempfile
import shutil
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.core.session import (
    get_or_create_session, 
    add_task, 
    update_task, 
    get_task,
    get_session_tasks,
    TaskResult
)
from app.core.executor import acquire_slot, release_slot
from app.engine.masker import get_engine
from app.engine.rules import get_rules_info
from app.engine.rule_service import rule_service
from app.engine.archive import detect_archive_type, ArchiveType

import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum upload file size (500 MB)
MAX_UPLOAD_SIZE = 500 * 1024 * 1024

# Supported file extensions (text extensions imported from archive module)
from app.engine.archive import TEXT_EXTENSIONS
ARCHIVE_EXTENSIONS = {'.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz', '.tar', '.zip'}


class MaskResponse(BaseModel):
    """Response model for masking result"""
    task_id: str
    session_id: str
    status: str
    filename: str
    message: str


class TaskStatusResponse(BaseModel):
    """Response model for task status"""
    task_id: str
    filename: str
    status: str
    progress: int
    created_at: float
    completed_at: Optional[float]
    error: Optional[str]
    report: Optional[dict]


@router.post("/mask", response_model=MaskResponse, summary="Upload and mask a file")
async def mask_file(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(..., description="File to mask"),
    whitelist: Optional[str] = Form(default="", description="Comma-separated whitelist"),
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID", description="Session ID")
):
    """Upload a file for masking. Supports text files and archives (.tgz, .zip, etc.)"""
    filename = file.filename.lower()
    
    # Check if archive file
    is_archive = False
    for ext in ARCHIVE_EXTENSIONS:
        if filename.endswith(ext):
            is_archive = True
            break
    
    # Check if text file
    is_text = Path(file.filename).suffix.lower() in TEXT_EXTENSIONS
    
    if not is_archive and not is_text:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed text: {', '.join(TEXT_EXTENSIONS)}. Allowed archives: {', '.join(ARCHIVE_EXTENSIONS)}"
        )
    
    # Get or create session
    session_id, session = get_or_create_session(x_session_id)
    
    # Create task
    task_id = str(uuid.uuid4())
    task = TaskResult(
        task_id=task_id,
        filename=file.filename,
        status="pending",
        created_at=time.time()
    )
    add_task(session_id, task)
    
    # Save uploaded file temporarily — sanitize filename to prevent path traversal
    safe_filename = os.path.basename(file.filename or "upload").strip() or "upload"
    temp_file_path = session.storage_path / f"upload_{task_id}_{safe_filename}"
    try:
        # Stream file in chunks to avoid OOM on large uploads
        total_bytes = 0
        chunk_size = 1024 * 1024  # 1 MB
        with open(temp_file_path, 'wb') as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE:
                    f.close()
                    temp_file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB."
                    )
                f.write(chunk)
    except HTTPException:
        update_task(session_id, task_id, status="failed", error="File too large")
        raise
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        update_task(session_id, task_id, status="failed", error="Failed to save file")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")
    
    # Parse whitelist
    whitelist_items = [w.strip() for w in whitelist.split(',') if w.strip()]

    # Extract org context from authenticated user (if any)
    auth_user = getattr(request.state, 'auth_user', None)
    caller_org_id = (auth_user.get('org_id') or 'default') if auth_user else 'default'
    caller_name = auth_user.get('name') if auth_user else None
    caller_role = auth_user.get('role', 'user') if auth_user else 'user'
    caller_key_prefix = auth_user.get('key_prefix') if auth_user else None

    # Add background task for processing
    background_tasks.add_task(
        process_masking_task,
        session_id=session_id,
        task_id=task_id,
        file_path=str(temp_file_path),
        filename=file.filename,
        whitelist=whitelist_items,
        storage_path=session.storage_path,
        is_archive=is_archive,
        caller_org_id=caller_org_id,
        caller_name=caller_name,
        caller_role=caller_role,
        caller_key_prefix=caller_key_prefix,
    )
    
    return MaskResponse(
        task_id=task_id,
        session_id=session_id,
        status="pending",
        filename=file.filename,
        message=f"{'Archive' if is_archive else 'File'} uploaded successfully. Processing started."
    )


async def process_masking_task(
    session_id: str,
    task_id: str,
    file_path: str,
    filename: str,
    whitelist: List[str],
    storage_path: Path,
    is_archive: bool = False,
    caller_org_id: str = 'default',
    caller_name: Optional[str] = None,
    caller_role: str = 'user',
    caller_key_prefix: Optional[str] = None,
):
    """Background task to process masking (supports both files and archives)"""
    try:
        # Acquire processing slot
        await acquire_slot()

        update_task(session_id, task_id, status="processing", progress=0)

        # Progress callback
        def on_progress(progress: int):
            update_task(session_id, task_id, progress=progress)

        # Load rules for this caller's org context (system + org + private)
        # Private rules matched by creator_key_prefix for security (name alone is not unique)
        rules = rule_service.get_enabled_rules_for(
            org_id=caller_org_id,
            owner=caller_name,
            role=caller_role,
            key_prefix=caller_key_prefix,
        )

        # Run masking (supports both regular files and archives)
        engine = get_engine()
        result = await engine.mask_file(
            file_path=file_path,
            output_dir=str(storage_path),
            whitelist=whitelist,
            progress_callback=on_progress,
            rules=rules,
        )
        
        # Get the masked file path
        masked_file_path = result.masked_file_path
        
        # Build report
        report = {
            "report_id": f"report-{task_id}",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "file_info": {
                "name": filename,
                "size_bytes": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                "is_archive": result.is_archive,
                "archive_type": result.archive_type,
                "files_processed": result.files_processed,
                "lines_total": result.total_lines
            },
            "summary": {
                "total_matches": result.total_matches,
                "risk_score": result.risk_score,
                "risk_level": result.risk_level,
                "processing_time_ms": result.processing_time_ms,
                "whitelist_skipped": result.whitelist_skipped
            },
            "breakdown": [
                {
                    "rule_id": stats.rule_id,
                    "rule_name": stats.rule_name,
                    "matches": stats.matches,
                    "examples": stats.examples
                }
                for stats in result.breakdown
            ]
        }
        
        # Update task as completed
        update_task(
            session_id, task_id,
            status="completed",
            progress=100,
            completed_at=time.time(),
            masked_file_path=masked_file_path,
            report=report
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        update_task(
            session_id, task_id,
            status="failed",
            error=str(e)
        )
    finally:
        release_slot()
        # Cleanup uploaded file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            logger.warning(f"Failed to clean up temp file: {file_path}")


@router.get("/task/{task_id}", response_model=TaskStatusResponse, summary="Get task status")
async def get_task_status(
    task_id: str,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID")
):
    """Get task processing status"""
    if not x_session_id:
        raise HTTPException(status_code=401, detail="Session ID required")
    
    task = get_task(x_session_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatusResponse(
        task_id=task.task_id,
        filename=task.filename,
        status=task.status,
        progress=task.progress,
        created_at=task.created_at,
        completed_at=task.completed_at,
        error=task.error,
        report=task.report
    )


@router.get("/tasks", summary="List all tasks")
async def list_tasks(
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID")
):
    """List all tasks in current session"""
    if not x_session_id:
        raise HTTPException(status_code=401, detail="Session ID required")
    
    tasks = get_session_tasks(x_session_id)
    
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "filename": t.filename,
                "status": t.status,
                "progress": t.progress,
                "created_at": t.created_at,
                "completed_at": t.completed_at,
                "total_matches": t.report.get("summary", {}).get("total_matches") if t.report else None,
                "risk_level": t.report.get("summary", {}).get("risk_level") if t.report else None
            }
            for t in tasks
        ]
    }


@router.get("/download/{task_id}", summary="Download masked file")
async def download_masked_file(
    task_id: str,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID")
):
    """Download the masked file"""
    if not x_session_id:
        raise HTTPException(status_code=401, detail="Session ID required")
    
    task = get_task(x_session_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not completed")
    
    if not task.masked_file_path or not Path(task.masked_file_path).exists():
        raise HTTPException(status_code=404, detail="Masked file not found")
    
    # Determine content type based on file extension
    masked_path = Path(task.masked_file_path)
    filename = masked_path.name
    
    # Set appropriate media type for archives
    media_type = "application/octet-stream"
    if filename.endswith('.tar.gz') or filename.endswith('.tgz'):
        media_type = "application/gzip"
    elif filename.endswith('.tar.bz2') or filename.endswith('.tbz2'):
        media_type = "application/x-bzip2"
    elif filename.endswith('.tar.xz') or filename.endswith('.txz'):
        media_type = "application/x-xz"
    elif filename.endswith('.zip'):
        media_type = "application/zip"
    elif filename.endswith('.tar'):
        media_type = "application/x-tar"
    
    return FileResponse(
        task.masked_file_path,
        filename=filename,
        media_type=media_type
    )


@router.get("/report/{task_id}", summary="Get masking report")
async def get_report(
    task_id: str,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID")
):
    """Get detailed masking report"""
    if not x_session_id:
        raise HTTPException(status_code=401, detail="Session ID required")
    
    task = get_task(x_session_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not completed")
    
    if not task.report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    return task.report


# Note: GET /rules is served by api/rules.py (rules management router)
