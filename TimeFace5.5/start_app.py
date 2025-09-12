#!/usr/bin/env python3
"""
Enhanced startup script for ZKTeco Attendance Management System
Handles port conflicts and provides better error handling
"""

import os
import sys
import socket
import subprocess
import time
from app import app, socketio, db
from websocket_events import start_device_monitor
import threading
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Remove device_manager import since it's not used in this file

def check_port_available(port):
    """Check if a port is available"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('0.0.0.0', port))
            return True
    except OSError:
        return False

def find_available_port(start_port=5001, max_attempts=10):
    """Find an available port starting from start_port"""
    for port in range(start_port, start_port + max_attempts):
        if check_port_available(port):
            return port
    return None

def kill_processes_on_port(port):
    """Kill processes using the specified port (Windows)"""
    try:
        # Find processes using the port
        result = subprocess.run(
            f'netstat -ano | findstr :{port}',
            shell=True, capture_output=True, text=True
        )
        
        if result.stdout:
            lines = result.stdout.strip().split('\n')
            pids = set()
            for line in lines:
                parts = line.split()
                if len(parts) >= 5 and 'LISTENING' in line:
                    pid = parts[-1]
                    pids.add(pid)
            
            for pid in pids:
                try:
                    subprocess.run(f'taskkill /PID {pid} /F', shell=True, check=True)
                    logging.info(f"Killed process {pid} using port {port}")
                except subprocess.CalledProcessError:
                    logging.warning(f"Could not kill process {pid}")
                    
    except Exception as e:
        logging.error(f"Error killing processes on port {port}: {e}")

def start_scheduler_service():
    """Start the scheduler service automatically"""
    try:
        # Check if scheduler is already running
        result = subprocess.run(['python', 'start_scheduler.py', 'status'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            logging.info("Scheduler service is already running")
            return True
        
        # Start scheduler service
        logging.info("Starting scheduler service...")
        result = subprocess.run(['python', 'start_scheduler.py', 'start'], 
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            logging.info("Scheduler service started successfully")
            return True
        else:
            logging.error(f"Failed to start scheduler service: {result.stderr}")
            return False
            
    except Exception as e:
        logging.error(f"Error starting scheduler service: {e}")
        return False

def main():
    """Main application startup function"""
    # Get preferred port from environment
    preferred_port = int(os.environ.get('PORT', 5001))
    
    # Check if preferred port is available
    if check_port_available(preferred_port):
        port = preferred_port
        logging.info(f"Using preferred port {port}")
    else:
        logging.warning(f"Port {preferred_port} is in use, looking for alternative...")
        
        # Try to kill processes on preferred port
        kill_processes_on_port(preferred_port)
        time.sleep(2)  # Wait a moment
        
        if check_port_available(preferred_port):
            port = preferred_port
            logging.info(f"Freed up preferred port {port}")
        else:
            # Find alternative port
            port = find_available_port(preferred_port + 1)
            if port is None:
                logging.error("No available ports found!")
                sys.exit(1)
            logging.info(f"Using alternative port {port}")
    
    try:
        # Start scheduler service automatically
        start_scheduler_service()
        
        # Start device status monitoring (only if not in debug mode to avoid double start)
        if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            start_device_monitor()

        logging.info(f"Starting ZKTeco Attendance Management System on http://0.0.0.0:{port}")
        logging.info("Scheduler service runs independently - check logs in scheduler_service.log")
        logging.info("Press Ctrl+C to stop the application")
        
        # Start the application
        socketio.run(app, host='0.0.0.0', port=port, debug=True)
        
    except KeyboardInterrupt:
        logging.info("Application stopped by user")
    except Exception as e:
        logging.error(f"Application startup failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
