"""
Thread Pool Executor for concurrent processing
Supports 16 concurrent masking tasks
"""
from concurrent.futures import ThreadPoolExecutor
from asyncio import Semaphore
import threading

# Global thread pool with 16 workers
MAX_WORKERS = 16
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# Concurrency limiter
_semaphore = Semaphore(MAX_WORKERS)
_active_tasks = 0
_lock = threading.Lock()


async def acquire_slot():
    """Acquire a processing slot"""
    global _active_tasks
    await _semaphore.acquire()
    with _lock:
        _active_tasks += 1


def release_slot():
    """Release a processing slot"""
    global _active_tasks
    _semaphore.release()
    with _lock:
        _active_tasks -= 1


def get_executor_status():
    """Get current executor status"""
    with _lock:
        return {
            "max_workers": MAX_WORKERS,
            "active_tasks": _active_tasks,
            "available_slots": MAX_WORKERS - _active_tasks
        }


def get_executor():
    """Get the global executor instance"""
    return executor


def shutdown_executor():
    """Shutdown the executor gracefully"""
    executor.shutdown(wait=True)
