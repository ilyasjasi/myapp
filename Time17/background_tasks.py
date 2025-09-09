import threading
import time
import logging
from datetime import datetime, timedelta
from app import app, db
from models import Device
from device_manager import DeviceManager
from cache_manager import device_cache, get_device_info_cached, invalidate_device_cache

class BackgroundTaskManager:
    """Manages background tasks for device updates and cache refresh"""
    
    def __init__(self):
        self.device_manager = DeviceManager()
        self.running = False
        self.threads = []
        
    def start(self):
        """Start background tasks"""
        if self.running:
            return
            
        self.running = True
        logging.info("Starting background tasks...")
        
        # Start device status update thread
        status_thread = threading.Thread(target=self._device_status_worker, daemon=True)
        status_thread.start()
        self.threads.append(status_thread)
        
        # Start cache cleanup thread
        cleanup_thread = threading.Thread(target=self._cache_cleanup_worker, daemon=True)
        cleanup_thread.start()
        self.threads.append(cleanup_thread)
        
        # Start device info refresh thread
        refresh_thread = threading.Thread(target=self._device_info_refresh_worker, daemon=True)
        refresh_thread.start()
        self.threads.append(refresh_thread)
        
    def stop(self):
        """Stop background tasks"""
        self.running = False
        logging.info("Stopping background tasks...")
        
    def _device_status_worker(self):
        """Background worker to update device online status"""
        while self.running:
            try:
                with app.app_context():
                    devices = Device.query.all()
                    for device in devices:
                        try:
                            # Quick online check
                            online = self.device_manager.is_device_online(device.ip_address)
                            if device.online_status != online:
                                device.online_status = online
                                # Invalidate cache when status changes
                                invalidate_device_cache(device.ip_address)
                                logging.info(f"Device {device.name} status changed to {'online' if online else 'offline'}")
                        except Exception as e:
                            logging.error(f"Error checking device {device.name} status: {e}")
                            device.online_status = False
                    
                    db.session.commit()
                    
            except Exception as e:
                logging.error(f"Error in device status worker: {e}")
            
            # Sleep for 60 seconds between checks
            time.sleep(60)
    
    def _cache_cleanup_worker(self):
        """Background worker to clean up expired cache entries"""
        while self.running:
            try:
                removed_count = device_cache.cleanup_expired()
                if removed_count > 0:
                    logging.debug(f"Cleaned up {removed_count} expired cache entries")
            except Exception as e:
                logging.error(f"Error in cache cleanup worker: {e}")
            
            # Sleep for 5 minutes between cleanups
            time.sleep(300)
    
    def _device_info_refresh_worker(self):
        """Background worker to refresh device info cache for online devices"""
        while self.running:
            try:
                with app.app_context():
                    # Only refresh info for online devices
                    online_devices = Device.query.filter_by(online_status=True).all()
                    
                    for device in online_devices:
                        try:
                            # Refresh device info in cache
                            get_device_info_cached(
                                self.device_manager, 
                                device.ip_address, 
                                ttl=600  # 10 minutes TTL for background refresh
                            )
                            logging.debug(f"Refreshed cache for device {device.name}")
                        except Exception as e:
                            logging.error(f"Error refreshing device {device.name} info: {e}")
                        
                        # Small delay between devices to avoid overwhelming network
                        time.sleep(2)
                        
            except Exception as e:
                logging.error(f"Error in device info refresh worker: {e}")
            
            # Sleep for 10 minutes between full refreshes
            time.sleep(600)

# Global background task manager
background_tasks = BackgroundTaskManager()

def start_background_tasks():
    """Start background tasks if not already running"""
    background_tasks.start()

def stop_background_tasks():
    """Stop background tasks"""
    background_tasks.stop()
