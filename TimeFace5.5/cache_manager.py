import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

class CacheManager:
    """Simple in-memory cache with TTL support for device information"""
    
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.default_ttl = 300  # 5 minutes default TTL
        
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                if time.time() < entry['expires_at']:
                    return entry['data']
                else:
                    # Remove expired entry
                    del self.cache[key]
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL"""
        if ttl is None:
            ttl = self.default_ttl
            
        with self.lock:
            self.cache[key] = {
                'data': value,
                'expires_at': time.time() + ttl,
                'created_at': time.time()
            }
    
    def delete(self, key: str) -> None:
        """Delete key from cache"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
    
    def clear(self) -> None:
        """Clear all cache entries"""
        with self.lock:
            self.cache.clear()
    
    def cleanup_expired(self) -> int:
        """Remove expired entries and return count of removed items"""
        current_time = time.time()
        removed_count = 0
        
        with self.lock:
            expired_keys = [
                key for key, entry in self.cache.items()
                if current_time >= entry['expires_at']
            ]
            
            for key in expired_keys:
                del self.cache[key]
                removed_count += 1
                
        return removed_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self.lock:
            current_time = time.time()
            total_entries = len(self.cache)
            expired_entries = sum(
                1 for entry in self.cache.values()
                if current_time >= entry['expires_at']
            )
            
            return {
                'total_entries': total_entries,
                'active_entries': total_entries - expired_entries,
                'expired_entries': expired_entries,
                'cache_keys': list(self.cache.keys())
            }

# Global cache instance
device_cache = CacheManager()

def get_device_info_cached(device_manager, ip_address: str, ttl: int = 300) -> Optional[Dict[str, Any]]:
    """Get device info with caching"""
    cache_key = f"device_info:{ip_address}"
    
    # Try to get from cache first
    cached_data = device_cache.get(cache_key)
    if cached_data is not None:
        logging.debug(f"Cache hit for device {ip_address}")
        return cached_data
    
    # Cache miss - fetch from device
    logging.debug(f"Cache miss for device {ip_address}, fetching from device")
    try:
        device_info = device_manager.get_device_info(ip_address)
        if device_info:
            # Cache the result
            device_cache.set(cache_key, device_info, ttl)
            return device_info
    except Exception as e:
        logging.error(f"Error fetching device info for {ip_address}: {e}")
    
    return None

def invalidate_device_cache(ip_address: str = None):
    """Invalidate device cache for specific IP or all devices"""
    if ip_address:
        cache_key = f"device_info:{ip_address}"
        device_cache.delete(cache_key)
        logging.info(f"Invalidated cache for device {ip_address}")
    else:
        device_cache.clear()
        logging.info("Cleared all device cache")
