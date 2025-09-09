#!/usr/bin/env python3
"""
Scheduler Service Starter Script
Use this to start the scheduler as a separate process
"""

import subprocess
import sys
import os
import time
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - STARTER - %(levelname)s - %(message)s'
)

def is_scheduler_running():
    """Check if scheduler service is already running"""
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
        # If psutil not available, check with simpler method
        return None

def start_scheduler_service():
    """Start the scheduler service as a separate process"""
    project_dir = Path(__file__).parent
    scheduler_script = project_dir / "scheduler_service.py"
    
    if not scheduler_script.exists():
        logging.error(f"Scheduler script not found: {scheduler_script}")
        return False
    
    # Check if already running
    existing_pid = is_scheduler_running()
    if existing_pid:
        logging.info(f"Scheduler service already running with PID: {existing_pid}")
        return True
    
    try:
        # Start scheduler as separate process
        cmd = [sys.executable, str(scheduler_script)]
        
        logging.info(f"Starting scheduler service: {' '.join(cmd)}")
        
        # Start process in background
        process = subprocess.Popen(
            cmd,
            cwd=str(project_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        
        # Give it a moment to start
        time.sleep(2)
        
        # Check if process is still running
        if process.poll() is None:
            logging.info(f"Scheduler service started successfully with PID: {process.pid}")
            
            # Save PID for later reference
            with open('scheduler.pid', 'w') as f:
                f.write(str(process.pid))
            
            return True
        else:
            stdout, stderr = process.communicate()
            logging.error(f"Scheduler service failed to start:")
            logging.error(f"STDOUT: {stdout.decode()}")
            logging.error(f"STDERR: {stderr.decode()}")
            return False
            
    except Exception as e:
        logging.error(f"Error starting scheduler service: {e}")
        return False

def stop_scheduler_service():
    """Stop the scheduler service"""
    try:
        # Try to read PID from file
        pid_file = Path('scheduler.pid')
        if pid_file.exists():
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            try:
                import psutil
                proc = psutil.Process(pid)
                proc.terminate()
                proc.wait(timeout=10)
                logging.info(f"Scheduler service stopped (PID: {pid})")
                pid_file.unlink()
                return True
            except ImportError:
                # Fallback for systems without psutil
                if os.name == 'nt':
                    os.system(f'taskkill /PID {pid} /F')
                else:
                    os.system(f'kill -TERM {pid}')
                pid_file.unlink()
                return True
            except Exception as e:
                logging.error(f"Error stopping scheduler: {e}")
                return False
        else:
            logging.warning("No PID file found, scheduler may not be running")
            return True
            
    except Exception as e:
        logging.error(f"Error stopping scheduler service: {e}")
        return False

def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'start':
            success = start_scheduler_service()
            sys.exit(0 if success else 1)
        elif command == 'stop':
            success = stop_scheduler_service()
            sys.exit(0 if success else 1)
        elif command == 'restart':
            stop_scheduler_service()
            time.sleep(2)
            success = start_scheduler_service()
            sys.exit(0 if success else 1)
        elif command == 'status':
            pid = is_scheduler_running()
            if pid:
                print(f"Scheduler service is running (PID: {pid})")
                sys.exit(0)
            else:
                print("Scheduler service is not running")
                sys.exit(1)
        else:
            print("Usage: python start_scheduler.py [start|stop|restart|status]")
            sys.exit(1)
    else:
        # Default action is to start
        success = start_scheduler_service()
        sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
