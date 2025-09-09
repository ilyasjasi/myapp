#!/usr/bin/env python3
"""
Scheduler Health Monitor
Monitors the scheduler service and restarts it if it crashes
"""

import time
import logging
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - MONITOR - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler_monitor.log'),
        logging.StreamHandler()
    ]
)

class SchedulerHealthMonitor:
    """Monitors scheduler service health and restarts if needed"""
    
    def __init__(self):
        self.project_dir = Path(__file__).parent
        self.check_interval = 60  # Check every minute
        self.max_restart_attempts = 3
        self.restart_cooldown = 300  # 5 minutes between restart attempts
        self.last_restart_time = None
        self.restart_count = 0
        
    def is_scheduler_running(self):
        """Check if scheduler service is running"""
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and 'scheduler_service.py' in ' '.join(cmdline):
                        return proc.info['pid']
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return None
        except ImportError:
            # Fallback: check PID file
            pid_file = self.project_dir / 'scheduler.pid'
            if pid_file.exists():
                try:
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    
                    # Check if process exists (Windows)
                    if os.name == 'nt':
                        result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                              capture_output=True, text=True)
                        return pid if str(pid) in result.stdout else None
                    else:
                        # Unix-like systems
                        try:
                            os.kill(pid, 0)
                            return pid
                        except OSError:
                            return None
                except:
                    return None
            return None
    
    def check_scheduler_health(self):
        """Check if scheduler is healthy by examining log file"""
        try:
            log_file = self.project_dir / 'scheduler_service.log'
            if not log_file.exists():
                return False
            
            # Check if there's been a health check in the last 10 minutes
            with open(log_file, 'r') as f:
                lines = f.readlines()
                
            # Look for recent health check
            for line in reversed(lines[-50:]):  # Check last 50 lines
                if 'health check - OK' in line:
                    try:
                        # Extract timestamp
                        timestamp_str = line.split(' - ')[0]
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        
                        # Check if it's within last 10 minutes
                        if datetime.now() - timestamp < timedelta(minutes=10):
                            return True
                    except:
                        continue
            
            return False
            
        except Exception as e:
            logging.error(f"Error checking scheduler health: {e}")
            return False
    
    def restart_scheduler(self):
        """Restart the scheduler service"""
        now = datetime.now()
        
        # Check cooldown period
        if (self.last_restart_time and 
            now - self.last_restart_time < timedelta(seconds=self.restart_cooldown)):
            logging.warning("Restart cooldown active, skipping restart")
            return False
        
        # Check max restart attempts
        if self.restart_count >= self.max_restart_attempts:
            logging.error(f"Max restart attempts ({self.max_restart_attempts}) reached")
            return False
        
        try:
            logging.info("Attempting to restart scheduler service...")
            
            # Stop scheduler
            stop_cmd = [sys.executable, 'start_scheduler.py', 'stop']
            subprocess.run(stop_cmd, cwd=self.project_dir, timeout=30)
            
            # Wait a moment
            time.sleep(5)
            
            # Start scheduler
            start_cmd = [sys.executable, 'start_scheduler.py', 'start']
            result = subprocess.run(start_cmd, cwd=self.project_dir, 
                                  capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                logging.info("Scheduler service restarted successfully")
                self.last_restart_time = now
                self.restart_count += 1
                return True
            else:
                logging.error(f"Failed to restart scheduler: {result.stderr}")
                return False
                
        except Exception as e:
            logging.error(f"Error restarting scheduler: {e}")
            return False
    
    def reset_restart_counter(self):
        """Reset restart counter after successful operation"""
        if self.restart_count > 0:
            logging.info("Scheduler running stable, resetting restart counter")
            self.restart_count = 0
    
    def monitor(self):
        """Main monitoring loop"""
        logging.info("Starting scheduler health monitor...")
        
        consecutive_healthy_checks = 0
        
        while True:
            try:
                # Check if scheduler process is running
                pid = self.is_scheduler_running()
                
                if not pid:
                    logging.warning("Scheduler process not found, attempting restart...")
                    self.restart_scheduler()
                    consecutive_healthy_checks = 0
                else:
                    # Process is running, check health
                    is_healthy = self.check_scheduler_health()
                    
                    if is_healthy:
                        logging.debug(f"Scheduler healthy (PID: {pid})")
                        consecutive_healthy_checks += 1
                        
                        # Reset restart counter after 5 consecutive healthy checks
                        if consecutive_healthy_checks >= 5:
                            self.reset_restart_counter()
                            consecutive_healthy_checks = 0
                    else:
                        logging.warning(f"Scheduler unhealthy (PID: {pid}), attempting restart...")
                        self.restart_scheduler()
                        consecutive_healthy_checks = 0
                
                # Wait before next check
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logging.info("Monitor stopped by user")
                break
            except Exception as e:
                logging.error(f"Monitor error: {e}")
                time.sleep(self.check_interval)

def main():
    """Main entry point"""
    monitor = SchedulerHealthMonitor()
    monitor.monitor()

if __name__ == '__main__':
    main()
