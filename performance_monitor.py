"""
NEURAL LENS - Real-time Performance Monitor
Advanced performance monitoring with metrics collection and analysis
"""

import psutil
import time
import threading
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Deque
import logging
import json

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and stores performance metrics over time"""
    
    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self.metrics: Dict[str, Deque] = {
            'cpu_percent': deque(maxlen=max_samples),
            'memory_percent': deque(maxlen=max_samples),
            'memory_mb': deque(maxlen=max_samples),
            'active_threads': deque(maxlen=max_samples),
            'request_count': deque(maxlen=max_samples),
            'avg_response_time': deque(maxlen=max_samples),
            'error_count': deque(maxlen=max_samples),
            'cache_hit_rate': deque(maxlen=max_samples),
            'db_query_time': deque(maxlen=max_samples),
            'face_recognition_fps': deque(maxlen=max_samples),
            'timestamps': deque(maxlen=max_samples)
        }
        self.lock = threading.RLock()
        self.request_counter = 0
        self.error_counter = 0
        self.response_times = []
        self.process = psutil.Process()
    
    def record_metric(self, metric_name: str, value: float):
        """Record a single metric value"""
        with self.lock:
            if metric_name in self.metrics:
                self.metrics[metric_name].append(value)
                self.metrics['timestamps'].append(time.time())
    
    def record_request(self, response_time: float, is_error: bool = False):
        """Record an API request"""
        with self.lock:
            self.request_counter += 1
            if is_error:
                self.error_counter += 1
            self.response_times.append(response_time)
            
            # Keep only last 1000 response times
            if len(self.response_times) > 1000:
                self.response_times = self.response_times[-1000:]
    
    def collect_system_metrics(self):
        """Collect current system metrics"""
        try:
            with self.lock:
                # CPU usage
                cpu_percent = self.process.cpu_percent(interval=0.1)
                self.record_metric('cpu_percent', cpu_percent)
                
                # Memory usage
                mem_info = self.process.memory_info()
                mem_mb = mem_info.rss / (1024 * 1024)
                mem_percent = self.process.memory_percent()
                self.record_metric('memory_mb', mem_mb)
                self.record_metric('memory_percent', mem_percent)
                
                # Thread count
                thread_count = threading.active_count()
                self.record_metric('active_threads', thread_count)
                
                # Request metrics
                self.record_metric('request_count', self.request_counter)
                self.record_metric('error_count', self.error_counter)
                
                # Average response time
                if self.response_times:
                    avg_time = sum(self.response_times[-100:]) / len(self.response_times[-100:])
                    self.record_metric('avg_response_time', avg_time * 1000)  # Convert to ms
                
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
    
    def get_current_metrics(self) -> Dict:
        """Get current snapshot of all metrics"""
        with self.lock:
            return {
                'cpu_percent': list(self.metrics['cpu_percent'])[-1] if self.metrics['cpu_percent'] else 0,
                'memory_mb': list(self.metrics['memory_mb'])[-1] if self.metrics['memory_mb'] else 0,
                'memory_percent': list(self.metrics['memory_percent'])[-1] if self.metrics['memory_percent'] else 0,
                'active_threads': list(self.metrics['active_threads'])[-1] if self.metrics['active_threads'] else 0,
                'total_requests': self.request_counter,
                'total_errors': self.error_counter,
                'avg_response_time_ms': list(self.metrics['avg_response_time'])[-1] if self.metrics['avg_response_time'] else 0,
                'error_rate': (self.error_counter / self.request_counter * 100) if self.request_counter > 0 else 0
            }
    
    def get_historical_metrics(self, window_size: int = 60) -> Dict:
        """Get metrics for the last N samples"""
        with self.lock:
            return {
                key: list(values)[-window_size:] if values else []
                for key, values in self.metrics.items()
            }
    
    def get_statistics(self) -> Dict:
        """Calculate statistics over collected metrics"""
        with self.lock:
            stats = {}
            
            for metric_name, values in self.metrics.items():
                if metric_name == 'timestamps' or not values:
                    continue
                
                values_list = list(values)
                stats[metric_name] = {
                    'current': values_list[-1] if values_list else 0,
                    'min': min(values_list) if values_list else 0,
                    'max': max(values_list) if values_list else 0,
                    'avg': sum(values_list) / len(values_list) if values_list else 0,
                    'samples': len(values_list)
                }
            
            return stats
    
    def reset(self):
        """Reset all metrics"""
        with self.lock:
            for values in self.metrics.values():
                values.clear()
            self.request_counter = 0
            self.error_counter = 0
            self.response_times = []


class PerformanceMonitor:
    """Real-time performance monitoring system"""
    
    def __init__(self, collection_interval: float = 1.0):
        self.collector = MetricsCollector()
        self.collection_interval = collection_interval
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.alerts: List[Dict] = []
        self.thresholds = {
            'cpu_percent': 80,
            'memory_percent': 85,
            'avg_response_time': 1.0,  # seconds
            'error_rate': 5.0  # percent
        }
    
    def start(self):
        """Start performance monitoring"""
        if not self.running:
            self.running = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("Performance monitoring started")
    
    def stop(self):
        """Stop performance monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Performance monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                self.collector.collect_system_metrics()
                self._check_thresholds()
                time.sleep(self.collection_interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
    
    def _check_thresholds(self):
        """Check if metrics exceed thresholds and create alerts"""
        metrics = self.collector.get_current_metrics()
        
        # CPU threshold
        if metrics['cpu_percent'] > self.thresholds['cpu_percent']:
            self._create_alert(
                'high_cpu',
                f"CPU usage at {metrics['cpu_percent']:.1f}%",
                'warning'
            )
        
        # Memory threshold
        if metrics['memory_percent'] > self.thresholds['memory_percent']:
            self._create_alert(
                'high_memory',
                f"Memory usage at {metrics['memory_percent']:.1f}%",
                'warning'
            )
        
        # Response time threshold
        if metrics['avg_response_time_ms'] / 1000 > self.thresholds['avg_response_time']:
            self._create_alert(
                'slow_response',
                f"Average response time at {metrics['avg_response_time_ms']:.0f}ms",
                'warning'
            )
        
        # Error rate threshold
        if metrics['error_rate'] > self.thresholds['error_rate']:
            self._create_alert(
                'high_error_rate',
                f"Error rate at {metrics['error_rate']:.1f}%",
                'critical'
            )
    
    def _create_alert(self, alert_type: str, message: str, severity: str):
        """Create a performance alert"""
        alert = {
            'type': alert_type,
            'message': message,
            'severity': severity,
            'timestamp': datetime.now().isoformat()
        }
        
        # Avoid duplicate alerts
        if not any(a['type'] == alert_type and a['severity'] == severity 
                   for a in self.alerts[-10:]):
            self.alerts.append(alert)
            logger.warning(f"Performance alert: {message}")
            
            # Keep only last 100 alerts
            if len(self.alerts) > 100:
                self.alerts = self.alerts[-100:]
    
    def get_dashboard_data(self) -> Dict:
        """Get formatted data for performance dashboard"""
        return {
            'current': self.collector.get_current_metrics(),
            'statistics': self.collector.get_statistics(),
            'alerts': self.alerts[-20:],  # Last 20 alerts
            'system_info': self.get_system_info()
        }
    
    def get_system_info(self) -> Dict:
        """Get system information"""
        try:
            return {
                'cpu_count': psutil.cpu_count(),
                'cpu_count_logical': psutil.cpu_count(logical=True),
                'total_memory_mb': psutil.virtual_memory().total / (1024 * 1024),
                'available_memory_mb': psutil.virtual_memory().available / (1024 * 1024),
                'disk_usage_percent': psutil.disk_usage('/').percent,
                'python_version': f"{psutil.Process().exe()}",
                'uptime_seconds': time.time() - psutil.Process().create_time()
            }
        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            return {}
    
    def record_request(self, response_time: float, is_error: bool = False):
        """Record an API request"""
        self.collector.record_request(response_time, is_error)
    
    def record_custom_metric(self, metric_name: str, value: float):
        """Record a custom metric"""
        self.collector.record_metric(metric_name, value)
    
    def export_metrics(self, format: str = 'json') -> str:
        """Export metrics in specified format"""
        if format == 'json':
            data = {
                'timestamp': datetime.now().isoformat(),
                'statistics': self.collector.get_statistics(),
                'current': self.collector.get_current_metrics(),
                'alerts': self.alerts[-50:]
            }
            return json.dumps(data, indent=2)
        elif format == 'prometheus':
            # Prometheus format
            lines = []
            current = self.collector.get_current_metrics()
            
            for key, value in current.items():
                metric_name = f"neural_lens_{key}"
                lines.append(f"# TYPE {metric_name} gauge")
                lines.append(f"{metric_name} {value}")
            
            return '\n'.join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")


# Global performance monitor instance
performance_monitor = PerformanceMonitor(collection_interval=1.0)


def start_monitoring():
    """Start the global performance monitor"""
    performance_monitor.start()


def stop_monitoring():
    """Stop the global performance monitor"""
    performance_monitor.stop()


# Flask middleware for automatic request tracking
class PerformanceMiddleware:
    """WSGI middleware for automatic performance tracking"""
    
    def __init__(self, app, monitor: PerformanceMonitor):
        self.app = app
        self.monitor = monitor
    
    def __call__(self, environ, start_response):
        start_time = time.time()
        
        def custom_start_response(status, headers, exc_info=None):
            # Record the response
            duration = time.time() - start_time
            is_error = not status.startswith('2')
            self.monitor.record_request(duration, is_error)
            
            return start_response(status, headers, exc_info)
        
        return self.app(environ, custom_start_response)


if __name__ == '__main__':
    # Test the performance monitor
    monitor = PerformanceMonitor(collection_interval=0.5)
    monitor.start()
    
    print("Performance monitoring started. Collecting metrics for 10 seconds...")
    
    # Simulate some requests
    for i in range(20):
        time.sleep(0.5)
        monitor.record_request(0.05 + (i % 5) * 0.01, is_error=(i % 10 == 0))
        
        if i % 2 == 0:
            print(f"\nCurrent metrics: {monitor.collector.get_current_metrics()}")
    
    print("\n" + "="*60)
    print("Final Statistics:")
    print("="*60)
    print(json.dumps(monitor.collector.get_statistics(), indent=2))
    
    print("\n" + "="*60)
    print("Alerts:")
    print("="*60)
    for alert in monitor.alerts:
        print(f"{alert['severity'].upper()}: {alert['message']} at {alert['timestamp']}")
    
    monitor.stop()
    print("\nPerformance monitoring test completed")
