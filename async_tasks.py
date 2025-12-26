"""
NEURAL LENS - Async Task Manager
Background task processing and job queue management
"""

import asyncio
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any, Optional, Dict, List
from datetime import datetime
import logging
from enum import Enum
import time
import uuid

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    """Represents a background task"""
    
    def __init__(self, task_id: str, func: Callable, *args, **kwargs):
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.status = TaskStatus.PENDING
        self.result: Optional[Any] = None
        self.error: Optional[Exception] = None
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.progress = 0.0
        self.metadata: Dict = {}
    
    def execute(self):
        """Execute the task"""
        try:
            self.status = TaskStatus.RUNNING
            self.started_at = datetime.now()
            
            logger.info(f"Executing task {self.task_id}")
            self.result = self.func(*self.args, **self.kwargs)
            
            self.status = TaskStatus.COMPLETED
            self.completed_at = datetime.now()
            self.progress = 100.0
            
            logger.info(f"Task {self.task_id} completed successfully")
            
        except Exception as e:
            self.status = TaskStatus.FAILED
            self.error = e
            self.completed_at = datetime.now()
            logger.error(f"Task {self.task_id} failed: {e}")
    
    def get_duration(self) -> float:
        """Get task execution duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
    
    def to_dict(self) -> Dict:
        """Convert task to dictionary"""
        return {
            'task_id': self.task_id,
            'status': self.status.value,
            'progress': self.progress,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration': self.get_duration(),
            'error': str(self.error) if self.error else None,
            'metadata': self.metadata
        }


class TaskQueue:
    """Priority task queue with worker pool"""
    
    def __init__(self, max_workers: int = 4, queue_size: int = 100):
        self.max_workers = max_workers
        self.task_queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=queue_size)
        self.tasks: Dict[str, Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.running = False
        self.worker_threads: List[threading.Thread] = []
        self.lock = threading.RLock()
    
    def start(self):
        """Start processing tasks"""
        if not self.running:
            self.running = True
            
            # Start worker threads
            for i in range(self.max_workers):
                thread = threading.Thread(target=self._worker, daemon=True, name=f"TaskWorker-{i}")
                thread.start()
                self.worker_threads.append(thread)
            
            logger.info(f"Task queue started with {self.max_workers} workers")
    
    def stop(self):
        """Stop processing tasks"""
        self.running = False
        
        # Wait for workers to finish
        for thread in self.worker_threads:
            thread.join(timeout=5)
        
        self.executor.shutdown(wait=True)
        logger.info("Task queue stopped")
    
    def _worker(self):
        """Worker thread that processes tasks"""
        while self.running:
            try:
                # Get task from queue with timeout
                try:
                    priority, task_id = self.task_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                with self.lock:
                    task = self.tasks.get(task_id)
                
                if task and task.status == TaskStatus.PENDING:
                    # Execute task
                    task.execute()
                
                self.task_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in task worker: {e}")
    
    def submit_task(self, func: Callable, *args, priority: int = 5, **kwargs) -> str:
        """
        Submit a task to the queue
        
        Args:
            func: Function to execute
            priority: Task priority (0 = highest, 10 = lowest)
            *args, **kwargs: Function arguments
        
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        task = Task(task_id, func, *args, **kwargs)
        
        with self.lock:
            self.tasks[task_id] = task
        
        # Add to queue with priority
        self.task_queue.put((priority, task_id))
        
        logger.info(f"Task {task_id} submitted with priority {priority}")
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get status of a task"""
        with self.lock:
            task = self.tasks.get(task_id)
            return task.to_dict() if task else None
    
    def get_task_result(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """
        Wait for task to complete and return result
        
        Args:
            task_id: Task identifier
            timeout: Maximum wait time in seconds
        
        Returns:
            Task result
        
        Raises:
            TimeoutError: If task doesn't complete in time
            Exception: If task failed
        """
        start_time = time.time()
        
        while True:
            with self.lock:
                task = self.tasks.get(task_id)
            
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            if task.status == TaskStatus.COMPLETED:
                return task.result
            
            if task.status == TaskStatus.FAILED:
                raise task.error
            
            if task.status == TaskStatus.CANCELLED:
                raise RuntimeError(f"Task {task_id} was cancelled")
            
            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")
            
            time.sleep(0.1)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task"""
        with self.lock:
            task = self.tasks.get(task_id)
            
            if task and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                logger.info(f"Task {task_id} cancelled")
                return True
        
        return False
    
    def get_queue_stats(self) -> Dict:
        """Get queue statistics"""
        with self.lock:
            pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
            running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
            completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
            failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
            
            return {
                'total_tasks': len(self.tasks),
                'pending': pending,
                'running': running,
                'completed': completed,
                'failed': failed,
                'queue_size': self.task_queue.qsize(),
                'max_workers': self.max_workers,
                'active_workers': running
            }
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Remove old completed/failed tasks"""
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        
        with self.lock:
            to_remove = [
                task_id for task_id, task in self.tasks.items()
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
                and task.completed_at
                and task.completed_at.timestamp() < cutoff_time
            ]
            
            for task_id in to_remove:
                del self.tasks[task_id]
            
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old tasks")


class BackgroundScheduler:
    """Schedule periodic background tasks"""
    
    def __init__(self):
        self.scheduled_tasks: Dict[str, Dict] = {}
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
    
    def start(self):
        """Start the scheduler"""
        if not self.running:
            self.running = True
            self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.scheduler_thread.start()
            logger.info("Background scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        logger.info("Background scheduler stopped")
    
    def schedule_task(self, name: str, func: Callable, interval_seconds: float, *args, **kwargs):
        """
        Schedule a task to run periodically
        
        Args:
            name: Task name
            func: Function to execute
            interval_seconds: Interval between executions
            *args, **kwargs: Function arguments
        """
        with self.lock:
            self.scheduled_tasks[name] = {
                'func': func,
                'interval': interval_seconds,
                'args': args,
                'kwargs': kwargs,
                'last_run': 0,
                'run_count': 0
            }
        
        logger.info(f"Scheduled task '{name}' to run every {interval_seconds}s")
    
    def unschedule_task(self, name: str):
        """Remove a scheduled task"""
        with self.lock:
            if name in self.scheduled_tasks:
                del self.scheduled_tasks[name]
                logger.info(f"Unscheduled task '{name}'")
    
    def _scheduler_loop(self):
        """Main scheduler loop"""
        while self.running:
            try:
                current_time = time.time()
                
                with self.lock:
                    tasks_to_run = []
                    
                    for name, task_info in self.scheduled_tasks.items():
                        time_since_last = current_time - task_info['last_run']
                        
                        if time_since_last >= task_info['interval']:
                            tasks_to_run.append((name, task_info))
                
                # Execute tasks outside of lock
                for name, task_info in tasks_to_run:
                    try:
                        logger.debug(f"Executing scheduled task: {name}")
                        task_info['func'](*task_info['args'], **task_info['kwargs'])
                        
                        with self.lock:
                            task_info['last_run'] = current_time
                            task_info['run_count'] += 1
                            
                    except Exception as e:
                        logger.error(f"Error in scheduled task '{name}': {e}")
                
                time.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(5)
    
    def get_scheduled_tasks(self) -> Dict:
        """Get information about scheduled tasks"""
        with self.lock:
            return {
                name: {
                    'interval': info['interval'],
                    'last_run': datetime.fromtimestamp(info['last_run']).isoformat() if info['last_run'] else None,
                    'run_count': info['run_count']
                }
                for name, info in self.scheduled_tasks.items()
            }


# Global instances
task_queue = TaskQueue(max_workers=4)
background_scheduler = BackgroundScheduler()


def start_background_services():
    """Start all background services"""
    task_queue.start()
    background_scheduler.start()
    logger.info("Background services started")


def stop_background_services():
    """Stop all background services"""
    task_queue.stop()
    background_scheduler.stop()
    logger.info("Background services stopped")


if __name__ == '__main__':
    # Test async task system
    import time
    
    def sample_task(duration: float, task_name: str):
        """Sample task that takes some time"""
        print(f"Task '{task_name}' started")
        time.sleep(duration)
        print(f"Task '{task_name}' completed")
        return f"Result from {task_name}"
    
    def periodic_task():
        """Sample periodic task"""
        print(f"Periodic task executed at {datetime.now()}")
    
    # Test task queue
    print("Testing Task Queue...")
    queue = TaskQueue(max_workers=2)
    queue.start()
    
    # Submit tasks
    task_ids = []
    for i in range(5):
        task_id = queue.submit_task(sample_task, 1.0, f"Task-{i}", priority=i)
        task_ids.append(task_id)
    
    # Wait and check results
    time.sleep(6)
    
    print("\nTask Results:")
    for task_id in task_ids:
        status = queue.get_task_status(task_id)
        if status:
            print(f"  {status['task_id'][:8]}: {status['status']} (duration: {status['duration']:.2f}s)")
    
    print(f"\nQueue Stats: {queue.get_queue_stats()}")
    
    # Test scheduler
    print("\n" + "="*60)
    print("Testing Background Scheduler...")
    
    scheduler = BackgroundScheduler()
    scheduler.start()
    
    scheduler.schedule_task('periodic', periodic_task, interval_seconds=2)
    
    time.sleep(7)
    
    print(f"\nScheduled Tasks: {scheduler.get_scheduled_tasks()}")
    
    # Cleanup
    queue.stop()
    scheduler.stop()
    
    print("\nAsync task system test completed")
