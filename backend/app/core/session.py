"""
Session management for user data isolation
Each user gets a unique session token to access only their own data
"""
import uuid
import time
import threading
from typing import Dict, Optional
from dataclasses import dataclass, field
from pathlib import Path
import shutil

# Session storage
_sessions: Dict[str, 'SessionData'] = {}
_lock = threading.Lock()

# Session expiry time (2 hours)
SESSION_EXPIRY_SECONDS = 7200

# Storage directory
STORAGE_DIR = Path("/tmp/masking-service")


@dataclass
class TaskResult:
    """Result of a masking task"""
    task_id: str
    filename: str
    status: str  # pending, processing, completed, failed
    created_at: float
    completed_at: Optional[float] = None
    masked_file_path: Optional[str] = None
    report: Optional[dict] = None
    error: Optional[str] = None
    progress: int = 0


@dataclass
class SessionData:
    """Session data for a user"""
    session_id: str
    created_at: float
    last_accessed: float
    tasks: Dict[str, TaskResult] = field(default_factory=dict)
    storage_path: Path = None
    
    def __post_init__(self):
        if self.storage_path is None:
            self.storage_path = STORAGE_DIR / self.session_id
            self.storage_path.mkdir(parents=True, exist_ok=True)


def create_session() -> str:
    """Create a new session and return the session ID"""
    session_id = str(uuid.uuid4())
    now = time.time()
    
    with _lock:
        _sessions[session_id] = SessionData(
            session_id=session_id,
            created_at=now,
            last_accessed=now
        )
    
    return session_id


def get_session(session_id: str) -> Optional[SessionData]:
    """Get session data by session ID"""
    with _lock:
        session = _sessions.get(session_id)
        if session:
            # Check if session expired
            if time.time() - session.last_accessed > SESSION_EXPIRY_SECONDS:
                # Clean up expired session
                _cleanup_session(session_id)
                return None
            # Update last accessed time
            session.last_accessed = time.time()
        return session


def get_or_create_session(session_id: Optional[str]) -> tuple[str, SessionData]:
    """Get existing session or create a new one"""
    if session_id:
        session = get_session(session_id)
        if session:
            return session_id, session
    
    # Create new session
    new_session_id = create_session()
    return new_session_id, _sessions[new_session_id]


def add_task(session_id: str, task: TaskResult):
    """Add a task to a session"""
    with _lock:
        session = _sessions.get(session_id)
        if session:
            session.tasks[task.task_id] = task


def update_task(session_id: str, task_id: str, **kwargs):
    """Update task data"""
    with _lock:
        session = _sessions.get(session_id)
        if session and task_id in session.tasks:
            task = session.tasks[task_id]
            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)


def get_task(session_id: str, task_id: str) -> Optional[TaskResult]:
    """Get a specific task from a session"""
    session = get_session(session_id)
    if session:
        return session.tasks.get(task_id)
    return None


def get_session_tasks(session_id: str) -> list[TaskResult]:
    """Get all tasks for a session (only user's own tasks)"""
    session = get_session(session_id)
    if session:
        # Return tasks sorted by creation time (newest first)
        return sorted(
            session.tasks.values(),
            key=lambda t: t.created_at,
            reverse=True
        )
    return []


def _cleanup_session(session_id: str):
    """Clean up session data and files"""
    session = _sessions.pop(session_id, None)
    if session and session.storage_path.exists():
        shutil.rmtree(session.storage_path, ignore_errors=True)


def cleanup_expired_sessions():
    """Clean up all expired sessions"""
    now = time.time()
    expired = []
    
    with _lock:
        for session_id, session in _sessions.items():
            if now - session.last_accessed > SESSION_EXPIRY_SECONDS:
                expired.append(session_id)
    
    for session_id in expired:
        _cleanup_session(session_id)


# Ensure storage directory exists
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
