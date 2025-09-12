#!/usr/bin/env python3
"""
Independent Scheduler Service
Runs separately from the main Flask application to prevent crashes
"""

import os
import sys
import time
import logging
import signal
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# Configure logging for scheduler service
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - SCHEDULER - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler_service.log'),
        logging.StreamHandler()
    ]
)

class SchedulerService:
    """Independent scheduler service that runs in its own process"""
    
    def __init__(self):
        self.running = False
        self.scheduler = None
        self.app = None
        self.db = None
        self.jobs_config = {}
        self.last_health_check = datetime.now()
        
    def setup_flask_context(self):
        """Setup Flask application context for database operations"""
        try:
            import sqlite3
            import os
            
            # Use absolute path for database to avoid path issues
            project_dir = Path(__file__).parent
            self.db_path = os.path.join(project_dir, "instance", "attendance.db")
            
            # Ensure instance directory exists
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # Test database connection
            conn = sqlite3.connect(self.db_path)
            conn.close()
            
            logging.info(f"Database connection setup completed: {self.db_path}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to setup database connection: {e}")
            return False
    
    def load_job_settings(self):
        """Load job settings from database or use defaults"""
        # Default settings
        self.jobs_config = {
            'csv_export_interval': 30,
            'employee_sync_time': '00:00',
            'terminate_sync_time': '01:00',
            'device_sync_interval': 5,
            'csv_export_path': 'exports/attendance_export.csv',
            'employee_csv_path': 'imports/employees.csv',
            'terminated_csv_path': 'imports/terminated.csv'
        }
        
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Try to load from database
            for key in self.jobs_config.keys():
                try:
                    cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
                    result = cursor.fetchone()
                    if result:
                        self.jobs_config[key] = result[0]
                except Exception as e:
                    logging.debug(f"Could not load setting {key}: {e}")
                    # Keep default value
                    pass
            
            conn.close()
            logging.info(f"Loaded job settings: {self.jobs_config}")
                
        except Exception as e:
            logging.warning(f"Using default settings due to error: {e}")
            # Keep default settings
    
    def safe_job_wrapper(self, job_func, job_name):
        """Wrapper to safely execute jobs with error handling"""
        def wrapper():
            start_time = datetime.now()
            logging.info(f"Starting job: {job_name}")
            
            try:
                job_func()
                    
                duration = (datetime.now() - start_time).total_seconds()
                logging.info(f"Job {job_name} completed successfully in {duration:.2f}s")
                
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                logging.error(f"Job {job_name} failed after {duration:.2f}s: {e}")
                
                # Log to database if possible
                try:
                    import sqlite3
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO job_executions (job_id, job_name, status, error_message, end_time)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        job_name.lower().replace(' ', '_'),
                        job_name,
                        'failed',
                        str(e),
                        datetime.utcnow().isoformat()
                    ))
                    conn.commit()
                    conn.close()
                except:
                    pass  # Don't let logging errors crash the scheduler
        
        return wrapper
    
    def export_attendance_csv_job(self):
        """Export attendance logs to CSV"""
        import pandas as pd
        import sqlite3
        import json
        
        job_id = 'csv_export'
        job_name = 'CSV Export'
        start_time = datetime.utcnow()
        
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        # Log job start
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, (job_id, job_name, 'running', start_time.isoformat()))
        execution_id = cursor.lastrowid
        conn.commit()
        
        try:
            csv_path = self.jobs_config.get('csv_export_path', 'exports/attendance_export.csv')
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            
            # Query unexported logs
            cursor.execute("""
                SELECT user_id, device_id, timestamp, status, area 
                FROM attendance_logs 
                WHERE exported_flag = 0 
                LIMIT 1000
            """)
            logs = cursor.fetchall()
            
            exported_count = 0
            all_data = []
            
            for log in logs:
                all_data.append({
                    'User ID': log[0],
                    'Device ID': log[1],
                    'Timestamp': log[2],
                    'Status': log[3],
                    'Area': log[4]
                })
                exported_count += 1
            
            if all_data:
                df = pd.DataFrame(all_data)
                df.to_csv(csv_path, index=False)
                logging.info(f"Exported {exported_count} records to {csv_path}")
                
                # Mark as exported
                cursor.execute("""
                    UPDATE attendance_logs 
                    SET exported_flag = 1 
                    WHERE exported_flag = 0 
                    AND id IN (
                        SELECT id FROM attendance_logs 
                        WHERE exported_flag = 0 
                        LIMIT 1000
                    )
                """)
            
            # Update job execution
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, result_data = ?
                WHERE id = ?
            """, (
                datetime.utcnow().isoformat(),
                'completed',
                json.dumps({'exported_count': exported_count}),
                execution_id
            ))
            conn.commit()
            
        except Exception as e:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, error_message = ?
                WHERE id = ?
            """, (
                datetime.utcnow().isoformat(),
                'failed',
                str(e),
                execution_id
            ))
            conn.commit()
            raise
        finally:
            conn.close()
    
    def import_employee_data_job(self):
        logging.info("Starting employee import job")
        import sqlite3
        import json
        import pandas as pd
        import os
        
        # Ensure job settings are loaded
        self.load_job_settings()
        
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        # Log job start
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, ('employee_import', 'Employee Import', 'running', datetime.now().isoformat()))
        execution_id = cursor.lastrowid
        conn.commit()
        
        try:
            csv_path = self.jobs_config.get('employee_csv_path', 'imports/employees.csv')
            imported_count = 0
            updated_count = 0
            
            if os.path.exists(csv_path):
                # Read CSV with header to properly map columns
                df = pd.read_csv(csv_path, on_bad_lines='skip')
                logging.info(f"Processing {len(df)} rows from {csv_path}")
                
                for _, row in df.iterrows():
                    try:
                        # Map columns based on CSV structure: EmployeeID is column 1
                        user_id = str(row.iloc[1]).strip() if len(row) > 1 and pd.notna(row.iloc[1]) else None
                        
                        if not user_id or user_id == 'nan' or user_id == 'EmployeeID':
                            continue
                        
                        first_name = str(row.iloc[2]).strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ''
                        last_name = str(row.iloc[3]).strip() if len(row) > 3 and pd.notna(row.iloc[3]) else ''
                        job_description = str(row.iloc[13]).strip() if len(row) > 13 and pd.notna(row.iloc[13]) else ''
                        status = str(row.iloc[27]).strip() if len(row) > 27 and pd.notna(row.iloc[27]) else 'Active'
                        site = str(row.iloc[10]).strip() if len(row) > 10 and pd.notna(row.iloc[10]) else ''
                        
                        # Check if user exists
                        cursor.execute("SELECT id FROM users WHERE user_id = ?", (user_id,))
                        existing_user = cursor.fetchone()
                        
                        if existing_user:
                            cursor.execute("""
                                UPDATE users SET 
                                first_name = COALESCE(NULLIF(?, ''), first_name),
                                last_name = COALESCE(NULLIF(?, ''), last_name),
                                job_description = COALESCE(NULLIF(?, ''), job_description),
                                status = ?,
                                site = COALESCE(NULLIF(?, ''), site)
                                WHERE user_id = ?
                            """, (first_name, last_name, job_description, status, site, user_id))
                            updated_count += 1
                        else:
                            cursor.execute("""
                                INSERT INTO users (user_id, first_name, last_name, job_description, status, site)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (user_id, first_name or f'User{user_id}', last_name, job_description, status, site))
                            imported_count += 1
                            
                    except Exception as e:
                        logging.error(f"Error processing employee row: {e}")
                        continue
                
                conn.commit()
                logging.info(f"Employee import: {imported_count} new, {updated_count} updated")
            
            # Update job execution
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, result_data = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'completed',
                json.dumps({
                    'imported_count': imported_count,
                    'updated_count': updated_count,
                    'warning': 'CSV file not found' if not os.path.exists(csv_path) else None
                }),
                execution_id
            ))
            conn.commit()
            
        except Exception as e:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, error_message = ?
                WHERE id = ?
            """, (
                datetime.utcnow().isoformat(),
                'failed',
                str(e),
                execution_id
            ))
            conn.commit()
            raise
        finally:
            conn.close()
    
    def terminate_employees_job(self):
        logging.info("Starting employee termination job")
        import sqlite3
        import json
        import pandas as pd
        import os
        
        # Ensure job settings are loaded
        self.load_job_settings()
        
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        # Log job start
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, ('employee_terminate', 'Employee Termination', 'running', datetime.now().isoformat()))
        execution_id = cursor.lastrowid
        conn.commit()
        
        try:
            csv_path = self.jobs_config.get('terminated_csv_path', 'imports/terminated.csv')
            terminated_count = 0
            
            if os.path.exists(csv_path):
                # Read CSV with header to properly map columns
                df = pd.read_csv(csv_path, on_bad_lines='skip')
                logging.info(f"Processing {len(df)} rows from termination CSV")
                
                for _, row in df.iterrows():
                    try:
                        # EmployeeID is in column 1, check EmploymentStatus in column 27
                        user_id = str(row.iloc[1]).strip() if len(row) > 1 and pd.notna(row.iloc[1]) else None
                        employment_status = str(row.iloc[27]).strip() if len(row) > 27 and pd.notna(row.iloc[27]) else ''
                        
                        if not user_id or user_id == 'EmployeeID1' or employment_status != 'Terminated':
                            continue
                            
                        cursor.execute("""
                            UPDATE users SET status = 'Terminated' 
                            WHERE user_id = ? AND status != 'Terminated'
                        """, (user_id,))
                        
                        if cursor.rowcount > 0:
                            terminated_count += 1
                            
                    except Exception as e:
                        logging.error(f"Error processing termination: {e}")
                        continue
                
                conn.commit()
            
            # Update job execution
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, result_data = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'completed',
                json.dumps({'terminated_count': terminated_count}),
                execution_id
            ))
            conn.commit()
            
        except Exception as e:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, error_message = ?
                WHERE id = ?
            """, (
                datetime.utcnow().isoformat(),
                'failed',
                str(e),
                execution_id
            ))
            conn.commit()
            raise
        finally:
            conn.close()
    
    def auto_log_collection_job(self):
        """Automatically collect logs from all connected devices every 3 minutes"""
        logging.info("Starting auto log collection job")
        import sqlite3
        import json
        from device_manager import DeviceManager
        
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        # Log job start
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, ('auto_log_collection', 'Auto Log Collection', 'running', datetime.now().isoformat()))
        execution_id = cursor.lastrowid
        conn.commit()
        
        try:
            device_manager = DeviceManager()
            
            # Get all online devices
            cursor.execute("SELECT ip_address FROM devices WHERE online_status = 1")
            device_ips = [row[0] for row in cursor.fetchall()]
            
            total_logs_collected = 0
            devices_processed = 0
            
            for ip_address in device_ips:
                try:
                    # Get device_id for this IP address
                    cursor.execute("SELECT id FROM devices WHERE ip_address = ?", (ip_address,))
                    device_row = cursor.fetchone()
                    if not device_row:
                        logging.warning(f"Device {ip_address} not found in database")
                        continue
                    
                    device_id = device_row[0]
                    
                    # Collect logs from device using the fixed function with device_id
                    logs_collected = device_manager.collect_logs_from_device(ip_address)
                    if logs_collected > 0:
                        total_logs_collected += logs_collected
                        devices_processed += 1
                        logging.info(f"Collected {logs_collected} logs from device {ip_address}")
                except Exception as e:
                    logging.warning(f"Failed to collect logs from device {ip_address}: {e}")
            
            # Update job execution
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, result_data = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'completed',
                json.dumps({
                    'total_logs_collected': total_logs_collected,
                    'devices_processed': devices_processed,
                    'total_devices': len(device_ips)
                }),
                execution_id
            ))
            conn.commit()
            
            logging.info(f"Auto log collection completed: {total_logs_collected} logs from {devices_processed}/{len(device_ips)} devices")
            
        except Exception as e:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, error_message = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'failed',
                str(e),
                execution_id
            ))
            conn.commit()
            raise
        finally:
            conn.close()
    
    def balance_devices_job(self):
        """Balance user and template distribution between devices"""
        logging.info("Starting device balancing job")
        import sqlite3
        import json
        from device_manager import DeviceManager
        
        # Ensure job settings are loaded
        self.load_job_settings()
        
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        # Log job start
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, ('device_balance', 'Device Balance', 'running', datetime.now().isoformat()))
        execution_id = cursor.lastrowid
        conn.commit()
        
        try:
            device_manager = DeviceManager()
            result = device_manager.balance_devices_in_area()
            
            # Update job execution
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, result_data = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'completed',
                json.dumps(result if result else {'synced_users': 0, 'synced_templates': 0}),
                execution_id
            ))
            conn.commit()
            
            logging.info(f"Device balancing completed: {result}")
            
        except Exception as e:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, error_message = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'failed',
                str(e),
                execution_id
            ))
            conn.commit()
            raise
        finally:
            conn.close()
    
    def device_sync_job(self):
        """Comprehensive device sync: sync users and templates TO devices, remove terminated users"""
        import sqlite3
        import json
        
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        # Log job start
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, ('auto_device_sync', 'Auto Device Sync', 'running', datetime.now().isoformat()))
        execution_id = cursor.lastrowid
        conn.commit()
        
        try:
            # Import device manager here to avoid circular imports
            from device_manager import DeviceManager
            device_mgr = DeviceManager()
            
            # Only sync 2 devices at a time to prevent overload, use round-robin rotation
            cursor.execute("""
                SELECT ip_address, id as device_id, area_id, name 
                FROM devices 
                WHERE online_status = 1 
                ORDER BY COALESCE(last_sync, '1970-01-01') ASC
                LIMIT 2
            """)
            devices = cursor.fetchall()
            
            total_results = {
                'synced_devices': 0,
                'total_users_collected': 0,
                'total_users_synced': 0,
                'total_templates_synced': 0,
                'total_terminated_removed': 0,
                'total_devices': len(devices),
                'errors': []
            }
            
            for device in devices:
                try:
                    ip_address, device_id, area_id, name = device
                    logging.info(f"Starting comprehensive sync for device {name} ({ip_address})")
                    
                    # Use enhanced area-based sync if device has area, otherwise individual sync
                    if area_id:
                        result = device_mgr.sync_devices_in_area(area_id)
                    else:
                        result = device_mgr.comprehensive_device_sync(ip_address, area_id)
                    
                    if result.get('success'):
                        total_results['synced_devices'] += 1
                        total_results['total_users_collected'] += result.get('users_collected', 0)
                        total_results['total_users_synced'] += result.get('users_synced', 0)
                        total_results['total_templates_synced'] += result.get('templates_synced', 0)
                        total_results['total_terminated_removed'] += result.get('terminated_removed', 0)
                        
                        logging.info(f"Completed sync for {name}: "
                                   f"{result.get('users_collected', 0)} users collected, "
                                   f"{result.get('users_synced', 0)} users synced, "
                                   f"{result.get('templates_synced', 0)} templates, "
                                   f"{result.get('terminated_removed', 0)} terminated removed")
                    else:
                        total_results['errors'].append(f"Device {name}: {result.get('error', 'Unknown error')}")
                        logging.error(f"Failed to sync device {name}: {result.get('error')}")
                    
                    # Update last sync time for rotation
                    cursor.execute("""
                        UPDATE devices 
                        SET last_sync = ? 
                        WHERE ip_address = ?
                    """, (datetime.now().isoformat(), ip_address))
                    conn.commit()
                    
                except Exception as e:
                    error_msg = f"Device {device[3] if len(device) > 3 else device[0]}: {str(e)}"
                    total_results['errors'].append(error_msg)
                    logging.error(f"Error syncing device {device[0] if device else 'unknown'}: {e}")
                    continue
            
            # Update job execution
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, result_data = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'completed',
                json.dumps(total_results),
                execution_id
            ))
            conn.commit()
            
            logging.info(f"Device sync job completed: {total_results['synced_devices']}/{total_results['total_devices']} devices, "
                        f"{total_results['total_users_collected']} users collected, {total_results['total_users_synced']} users synced, "
                        f"{total_results['total_templates_synced']} templates synced")
            
        except Exception as e:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, error_message = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'failed',
                str(e),
                execution_id
            ))
            conn.commit()
            logging.error(f"Device sync job failed: {e}")
            raise
        finally:
            conn.close()
    
    def health_check_job(self):
        """Periodic health check job"""
        logging.info("Starting health check job")
        import sqlite3
        import json
        
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        # Log job start
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, ('health_check', 'Health Check', 'running', datetime.now().isoformat()))
        execution_id = cursor.lastrowid
        conn.commit()
        
        try:
            self.last_health_check = datetime.now()
            
            # Check database connection
            cursor.execute("SELECT COUNT(*) FROM devices")
            device_count = cursor.fetchone()[0]
            
            # Update job execution
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, result_data = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'completed',
                json.dumps({'device_count': device_count, 'status': 'healthy'}),
                execution_id
            ))
            conn.commit()
            
            logging.info(f"Health check completed - {device_count} devices in database")
            
        except Exception as e:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, error_message = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                'failed',
                str(e),
                execution_id
            ))
            conn.commit()
            raise
        finally:
            conn.close()
    
    def start(self):
        """Start the scheduler service"""
        if self.running:
            logging.warning("Scheduler service already running")
            return
        
        logging.info("Starting Scheduler Service...")
        
        # Setup Flask context
        if not self.setup_flask_context():
            logging.error("Failed to setup Flask context")
            return False
        
        # Load job settings
        self.load_job_settings()
        
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from pytz import timezone
            
            # Use Dubai timezone
            dubai_tz = timezone('Asia/Dubai')
            
            self.scheduler = BlockingScheduler(
                timezone=dubai_tz,
                job_defaults={
                    'coalesce': True,
                    'max_instances': 1,
                    'misfire_grace_time': 60
                }
            )
            
            # Schedule jobs based on configuration
            try:
                # CSV Export job - every X minutes
                csv_interval = int(self.jobs_config.get('csv_export_interval', 30))
                self.scheduler.add_job(
                    func=self.safe_job_wrapper(self.export_attendance_csv_job, 'CSV Export'),
                    trigger="interval",
                    minutes=csv_interval,
                    id='csv_export',
                    replace_existing=True
                )
                logging.info(f"Scheduled CSV export every {csv_interval} minutes")

                # Employee import job - daily at specified time
                employee_sync_time = self.jobs_config.get('employee_sync_time', '00:00')
                hour, minute = map(int, employee_sync_time.split(':'))
                self.scheduler.add_job(
                    func=self.safe_job_wrapper(self.import_employee_data_job, 'Employee Import'),
                    trigger="cron",
                    hour=hour,
                    minute=minute,
                    id='employee_import',
                    replace_existing=True
                )
                logging.info(f"Scheduled employee import daily at {employee_sync_time}")

                # Employee termination job - daily at specified time
                terminate_sync_time = self.jobs_config.get('terminate_sync_time', '01:00')
                hour, minute = map(int, terminate_sync_time.split(':'))
                self.scheduler.add_job(
                    func=self.safe_job_wrapper(self.terminate_employees_job, 'Employee Termination'),
                    trigger="cron",
                    hour=hour,
                    minute=minute,
                    id='employee_terminate',
                    replace_existing=True
                )
                logging.info(f"Scheduled employee termination daily at {terminate_sync_time}")

                # Auto log collection job - every 10 minutes (reduced from 3)
                self.scheduler.add_job(
                    func=self.safe_job_wrapper(self.auto_log_collection_job, 'Auto Log Collection'),
                    trigger="interval",
                    minutes=10,
                    id='auto_log_collection',
                    replace_existing=True
                )
                logging.info("Scheduled auto log collection every 10 minutes")

                # Device sync job - every 1 hour (60 minutes)
                device_sync_interval = int(self.jobs_config.get('device_sync_interval', 60))
                self.scheduler.add_job(
                    func=self.safe_job_wrapper(self.device_sync_job, 'Device Sync'),
                    trigger="interval",
                    minutes=device_sync_interval,
                    id='auto_device_sync',
                    replace_existing=True
                )
                logging.info(f"Scheduled device sync every {device_sync_interval} minutes")

                # Health check job - every 15 minutes (reduced from 5)
                self.scheduler.add_job(
                    func=self.safe_job_wrapper(self.health_check_job, 'Health Check'),
                    trigger="interval",
                    minutes=15,
                    id='health_check',
                    replace_existing=True
                )
                logging.info("Scheduled health check every 15 minutes")
                
                logging.info(f"Scheduler configured - CSV: {csv_interval}min, Import: {hour:02d}:{minute:02d}, Terminate: {hour:02d}:{minute:02d}, Device sync: {device_sync_interval}min")
                
                # Start scheduler (this blocks)
                self.scheduler.start()
                
            except Exception as e:
                logging.error(f"Failed to schedule jobs: {e}")
                self.running = False
                return False
            
            self.running = True
            
        except Exception as e:
            logging.error(f"Failed to start scheduler: {e}")
            self.running = False
            return False
    
    def stop(self):
        """Stop the scheduler service"""
        if self.scheduler and self.running:
            logging.info("Stopping scheduler service...")
            self.scheduler.shutdown(wait=False)
            self.running = False
            logging.info("Scheduler service stopped")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logging.info(f"Received signal {signum}, shutting down...")
    if scheduler_service:
        scheduler_service.stop()
    sys.exit(0)

# Global scheduler service instance
scheduler_service = None

def main():
    """Main entry point for scheduler service"""
    global scheduler_service
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logging.info("Initializing Scheduler Service...")
    
    scheduler_service = SchedulerService()
    
    try:
        scheduler_service.start()
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt")
    except Exception as e:
        logging.error(f"Scheduler service error: {e}")
    finally:
        if scheduler_service:
            scheduler_service.stop()

if __name__ == '__main__':
    main()
