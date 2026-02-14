"""
Background job system for long-running tasks.
Implements a lightweight task queue with status tracking and completion notifications.
"""
import queue
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class JobStatus(Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Represents a background job."""
    job_id: str
    name: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    result: Any = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: float = 0.0
    progress_message: str = ""


class BackgroundJobManager:
    """Manages background job execution with a worker thread pool."""
    
    def __init__(self, max_workers: int = 2):
        """
        Initialize the job manager.
        
        Args:
            max_workers: Maximum number of concurrent worker threads
        """
        self.max_workers = max_workers
        self.job_queue = queue.Queue()
        self.jobs: dict[str, Job] = {}
        self.workers: list = []
        self.running = False
        self._lock = threading.Lock()
        
    def start(self):
        """Start the worker threads."""
        if self.running:
            return
            
        self.running = True
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker_loop, daemon=True, name=f"JobWorker-{i}")
            worker.start()
            self.workers.append(worker)
    
    def stop(self):
        """Stop all worker threads."""
        self.running = False
        # Add None sentinel values to unblock workers
        for _ in range(self.max_workers):
            self.job_queue.put(None)
        
        for worker in self.workers:
            worker.join(timeout=5)
        self.workers.clear()
    
    def submit_job(
        self,
        func: Callable,
        name: str,
        *args,
        **kwargs
    ) -> str:
        """
        Submit a new job for background execution.
        
        Args:
            func: Function to execute
            name: Human-readable job name
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            str: Unique job ID
        """
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            name=name,
            func=func,
            args=args,
            kwargs=kwargs
        )
        
        with self._lock:
            self.jobs[job_id] = job
        
        self.job_queue.put(job_id)
        return job_id
    
    def get_job(self, job_id: str) -> Job | None:
        """Get job information by ID."""
        with self._lock:
            return self.jobs.get(job_id)
    
    def get_all_jobs(self) -> dict[str, Job]:
        """Get all jobs."""
        with self._lock:
            return dict(self.jobs)
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending job.
        
        Args:
            job_id: Job ID to cancel
            
        Returns:
            bool: True if cancelled, False if job is already running/completed
        """
        with self._lock:
            job = self.jobs.get(job_id)
            if job and job.status == JobStatus.PENDING:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now()
                return True
        return False
    
    def update_progress(self, job_id: str, progress: float, message: str = ""):
        """
        Update job progress (called from within job function).
        
        Args:
            job_id: Job ID
            progress: Progress value (0.0 to 1.0)
            message: Optional progress message
        """
        with self._lock:
            job = self.jobs.get(job_id)
            if job:
                job.progress = min(max(progress, 0.0), 1.0)
                job.progress_message = message
    
    def _worker_loop(self):
        """Main worker loop that processes jobs from the queue."""
        while self.running:
            try:
                # Get next job (blocking with timeout)
                job_id = self.job_queue.get(timeout=1)
                
                # None is our sentinel value to stop
                if job_id is None:
                    break
                
                with self._lock:
                    job = self.jobs.get(job_id)
                
                if not job or job.status == JobStatus.CANCELLED:
                    continue
                
                # Mark as running
                with self._lock:
                    job.status = JobStatus.RUNNING
                    job.started_at = datetime.now()
                
                try:
                    # Execute the job function
                    result = job.func(*job.args, **job.kwargs)
                    
                    # Mark as completed
                    with self._lock:
                        job.status = JobStatus.COMPLETED
                        job.result = result
                        job.completed_at = datetime.now()
                        job.progress = 1.0
                        
                except Exception as e:
                    # Mark as failed
                    with self._lock:
                        job.status = JobStatus.FAILED
                        job.error = str(e)
                        job.completed_at = datetime.now()
                
                finally:
                    self.job_queue.task_done()
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Worker error: {e}")
    
    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """
        Remove completed/failed jobs older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age in hours for completed jobs
        """
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
        
        with self._lock:
            to_remove = []
            for job_id, job in self.jobs.items():
                if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    if job.completed_at and job.completed_at.timestamp() < cutoff:
                        to_remove.append(job_id)
            
            for job_id in to_remove:
                del self.jobs[job_id]


# Global singleton instance
_job_manager: BackgroundJobManager | None = None


def get_job_manager() -> BackgroundJobManager:
    """Get or create the global job manager instance."""
    global _job_manager
    if _job_manager is None:
        _job_manager = BackgroundJobManager(max_workers=2)
        _job_manager.start()
    return _job_manager


def submit_background_job(func: Callable, name: str, *args, **kwargs) -> str:
    """
    Convenience function to submit a background job.
    
    Args:
        func: Function to execute
        name: Human-readable job name
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func
        
    Returns:
        str: Unique job ID
    """
    manager = get_job_manager()
    return manager.submit_job(func, name, *args, **kwargs)
