"""
System Health Monitoring and Watchdog Service
Monitors system resources, process health, and provides automatic recovery
"""

import psutil
import logging
import time
import threading
from typing import Dict, Callable, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status enumeration"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ProcessInfo:
    """Process monitoring information"""
    process_id: str
    timeout: int  # seconds
    last_heartbeat: datetime = field(default_factory=datetime.now)
    restart_callback: Optional[Callable] = None
    restart_count: int = 0
    max_restarts: int = 3


@dataclass
class HealthMetrics:
    """System health metrics"""
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    disk_percent: float
    disk_free_gb: float
    temperature: Optional[float]
    status: HealthStatus
    timestamp: datetime = field(default_factory=datetime.now)


class WatchdogMonitor:
    """
    Watchdog monitor for system health and process supervision
    """
    
    def __init__(self, check_interval: int = 10):
        """
        Initialize watchdog monitor
        
        Args:
            check_interval: Health check interval in seconds
        """
        self.check_interval = check_interval
        self.processes: Dict[str, ProcessInfo] = {}
        self.health_history: list = []
        self.max_history = 1000
        
        # Thresholds
        self.cpu_warning_threshold = 70.0
        self.cpu_critical_threshold = 90.0
        self.memory_warning_threshold = 70.0
        self.memory_critical_threshold = 85.0
        self.disk_warning_threshold = 80.0
        self.disk_critical_threshold = 95.0
        self.temp_warning_threshold = 70.0
        self.temp_critical_threshold = 85.0
        
        # Monitoring state
        self._running = False
        self._monitor_thread = None
        
        logger.info("Watchdog Monitor initialized")
    
    def register_process(self, process_id: str, timeout: int, 
                        restart_callback: Optional[Callable] = None,
                        max_restarts: int = 3) -> None:
        """
        Register a process for monitoring
        
        Args:
            process_id: Unique process identifier
            timeout: Timeout in seconds for heartbeat
            restart_callback: Function to call for process restart
            max_restarts: Maximum automatic restart attempts
        """
        self.processes[process_id] = ProcessInfo(
            process_id=process_id,
            timeout=timeout,
            restart_callback=restart_callback,
            max_restarts=max_restarts
        )
        logger.info(f"Registered process: {process_id} (timeout={timeout}s)")
    
    def unregister_process(self, process_id: str) -> None:
        """Unregister a process from monitoring"""
        if process_id in self.processes:
            del self.processes[process_id]
            logger.info(f"Unregistered process: {process_id}")
    
    def heartbeat(self, process_id: str) -> None:
        """
        Update heartbeat for a process
        
        Args:
            process_id: Process identifier
        """
        if process_id in self.processes:
            self.processes[process_id].last_heartbeat = datetime.now()
    
    def get_system_metrics(self) -> HealthMetrics:
        """Get current system health metrics"""
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_available_mb = memory.available / (1024 * 1024)
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_free_gb = disk.free / (1024 * 1024 * 1024)
        
        # Temperature (if available)
        temperature = None
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Get first available temperature sensor
                for name, entries in temps.items():
                    if entries:
                        temperature = entries[0].current
                        break
        except (AttributeError, OSError):
            pass  # Temperature sensors not available
        
        # Determine overall status
        status = self._determine_health_status(
            cpu_percent, memory_percent, disk_percent, temperature
        )
        
        metrics = HealthMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_available_mb=memory_available_mb,
            disk_percent=disk_percent,
            disk_free_gb=disk_free_gb,
            temperature=temperature,
            status=status
        )
        
        # Add to history
        self.health_history.append(metrics)
        if len(self.health_history) > self.max_history:
            self.health_history.pop(0)
        
        return metrics
    
    def _determine_health_status(self, cpu: float, memory: float, 
                                 disk: float, temp: Optional[float]) -> HealthStatus:
        """Determine overall health status from metrics"""
        # Check critical conditions
        if (cpu >= self.cpu_critical_threshold or 
            memory >= self.memory_critical_threshold or
            disk >= self.disk_critical_threshold or
            (temp and temp >= self.temp_critical_threshold)):
            return HealthStatus.CRITICAL
        
        # Check warning conditions
        if (cpu >= self.cpu_warning_threshold or
            memory >= self.memory_warning_threshold or
            disk >= self.disk_warning_threshold or
            (temp and temp >= self.temp_warning_threshold)):
            return HealthStatus.WARNING
        
        return HealthStatus.HEALTHY
    
    def check_process_health(self) -> Dict[str, bool]:
        """Check health of all registered processes"""
        current_time = datetime.now()
        process_status = {}
        
        for process_id, info in self.processes.items():
            time_since_heartbeat = (current_time - info.last_heartbeat).total_seconds()
            is_healthy = time_since_heartbeat < info.timeout
            
            process_status[process_id] = is_healthy
            
            if not is_healthy:
                logger.warning(
                    f"Process {process_id} timeout "
                    f"(last heartbeat: {time_since_heartbeat:.1f}s ago)"
                )
                
                # Attempt automatic restart if configured
                if info.restart_callback and info.restart_count < info.max_restarts:
                    logger.info(f"Attempting to restart process: {process_id}")
                    try:
                        info.restart_callback()
                        info.restart_count += 1
                        info.last_heartbeat = datetime.now()
                        logger.info(f"Process {process_id} restarted successfully")
                    except Exception as e:
                        logger.error(f"Failed to restart process {process_id}: {e}")
                elif info.restart_count >= info.max_restarts:
                    logger.error(
                        f"Process {process_id} exceeded maximum restart attempts "
                        f"({info.max_restarts})"
                    )
        
        return process_status
    
    def get_health_report(self) -> Dict:
        """Get comprehensive health report"""
        metrics = self.get_system_metrics()
        process_status = self.check_process_health()
        
        return {
            'system': {
                'cpu_percent': metrics.cpu_percent,
                'memory_percent': metrics.memory_percent,
                'memory_available_mb': metrics.memory_available_mb,
                'disk_percent': metrics.disk_percent,
                'disk_free_gb': metrics.disk_free_gb,
                'temperature': metrics.temperature,
                'status': metrics.status.value,
                'timestamp': metrics.timestamp.isoformat()
            },
            'processes': {
                pid: {
                    'healthy': status,
                    'last_heartbeat': info.last_heartbeat.isoformat(),
                    'restart_count': info.restart_count
                }
                for pid, (status, info) in zip(
                    process_status.keys(),
                    [(s, self.processes[pid]) for pid, s in process_status.items()]
                )
            },
            'overall_status': metrics.status.value
        }
    
    def start_monitoring(self) -> None:
        """Start continuous health monitoring"""
        if self._running:
            logger.warning("Monitoring already running")
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Watchdog monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop health monitoring"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Watchdog monitoring stopped")
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop"""
        while self._running:
            try:
                report = self.get_health_report()
                
                # Log warnings and critical conditions
                if report['overall_status'] == HealthStatus.CRITICAL.value:
                    logger.critical(f"CRITICAL system health: {report['system']}")
                elif report['overall_status'] == HealthStatus.WARNING.value:
                    logger.warning(f"WARNING system health: {report['system']}")
                
                # Check for unhealthy processes
                for process_id, status in report['processes'].items():
                    if not status['healthy']:
                        logger.warning(f"Unhealthy process: {process_id}")
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            time.sleep(self.check_interval)
    
    def get_health_history(self, minutes: int = 60) -> list:
        """Get health history for the specified duration"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [
            m for m in self.health_history 
            if m.timestamp >= cutoff_time
        ]


# Singleton instance
_watchdog_instance = None


def get_watchdog() -> WatchdogMonitor:
    """Get singleton watchdog instance"""
    global _watchdog_instance
    if _watchdog_instance is None:
        _watchdog_instance = WatchdogMonitor()
    return _watchdog_instance


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create watchdog
    watchdog = get_watchdog()
    
    # Register a mock process
    def restart_process():
        print("Restarting process...")
    
    watchdog.register_process("test_process", timeout=30, restart_callback=restart_process)
    
    # Start monitoring
    watchdog.start_monitoring()
    
    # Simulate heartbeats
    for i in range(5):
        time.sleep(5)
        watchdog.heartbeat("test_process")
        report = watchdog.get_health_report()
        print(f"\n=== Health Report ===")
        print(f"System Status: {report['overall_status']}")
        print(f"CPU: {report['system']['cpu_percent']:.1f}%")
        print(f"Memory: {report['system']['memory_percent']:.1f}%")
        print(f"Disk: {report['system']['disk_percent']:.1f}%")
    
    watchdog.stop_monitoring()
