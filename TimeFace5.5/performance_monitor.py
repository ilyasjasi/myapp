import time
import functools
import logging
from flask import request, g
from datetime import datetime

class PerformanceMonitor:
    """Simple performance monitoring for Flask routes"""
    
    def __init__(self):
        self.slow_queries = []
        self.request_times = {}
        
    def monitor_route(self, threshold=1.0):
        """Decorator to monitor route performance"""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    end_time = time.time()
                    duration = end_time - start_time
                    
                    # Log slow requests
                    if duration > threshold:
                        route_info = {
                            'route': request.endpoint,
                            'method': request.method,
                            'duration': duration,
                            'timestamp': datetime.now(),
                            'args': dict(request.args),
                            'remote_addr': request.remote_addr
                        }
                        self.slow_queries.append(route_info)
                        logging.warning(f"Slow route detected: {request.endpoint} took {duration:.2f}s")
                    
                    # Track route performance
                    route_key = f"{request.method} {request.endpoint}"
                    if route_key not in self.request_times:
                        self.request_times[route_key] = []
                    
                    self.request_times[route_key].append(duration)
                    
                    # Keep only last 100 requests per route
                    if len(self.request_times[route_key]) > 100:
                        self.request_times[route_key] = self.request_times[route_key][-100:]
            
            return wrapper
        return decorator
    
    def get_stats(self):
        """Get performance statistics"""
        stats = {}
        
        for route, times in self.request_times.items():
            if times:
                stats[route] = {
                    'count': len(times),
                    'avg_time': sum(times) / len(times),
                    'max_time': max(times),
                    'min_time': min(times),
                    'recent_avg': sum(times[-10:]) / min(len(times), 10)
                }
        
        return {
            'route_stats': stats,
            'slow_queries': self.slow_queries[-20:],  # Last 20 slow queries
            'total_slow_queries': len(self.slow_queries)
        }
    
    def clear_stats(self):
        """Clear performance statistics"""
        self.slow_queries.clear()
        self.request_times.clear()

# Global performance monitor instance
perf_monitor = PerformanceMonitor()

def init_performance_monitoring(app):
    """Initialize performance monitoring for Flask app"""
    
    @app.before_request
    def before_request():
        g.start_time = time.time()
    
    @app.after_request
    def after_request(response):
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            
            # Log very slow requests
            if duration > 2.0:
                logging.warning(f"Very slow request: {request.endpoint} took {duration:.2f}s")
        
        return response
