import logging
import pandas as pd
import os
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from app import db
from models import AttendanceLog, User, AppSetting
from utils import get_setting

def export_attendance_csv():
    """Export attendance logs to CSV every 30 minutes"""
    try:
        csv_path = get_setting('csv_export_path', '/tmp/ZKHours.csv')
        
        # Get unexported logs
        logs = AttendanceLog.query.filter_by(exported_flag=False).all()
        
        if not logs:
            logging.info("No new logs to export")
            return
        
        # Prepare data for CSV
        data = []
        for log in logs:
            user = User.query.filter_by(user_id=log.user_id).first()
            data.append({
                'User ID': log.user_id,
                'Name': f"{user.first_name} {user.last_name}" if user else 'Unknown',
                'Timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'Status': log.status,
                'Device ID': log.device_id,
                'Area': log.area
            })
        
        df = pd.DataFrame(data)
        
        # Append to existing file or create new one
        if os.path.exists(csv_path):
            df.to_csv(csv_path, mode='a', header=False, index=False)
        else:
            df.to_csv(csv_path, index=False)
        
        # Mark logs as exported
        for log in logs:
            log.exported_flag = True
        
        db.session.commit()
        logging.info(f"Exported {len(logs)} logs to {csv_path}")
        
    except Exception as e:
        logging.error(f"Error exporting CSV: {str(e)}")

def sync_employee_data():
    """Sync employee data from external CSV"""
    try:
        employee_csv_path = get_setting('employee_csv_path', '/tmp/employees.csv')
        terminated_csv_path = get_setting('terminated_csv_path', '/tmp/terminated.csv')
        
        # Sync active employees
        if os.path.exists(employee_csv_path):
            df_employees = pd.read_csv(employee_csv_path)
            
            for _, row in df_employees.iterrows():
                user = User.query.filter_by(user_id=str(row['user_id'])).first()
                
                if not user:
                    user = User(
                        user_id=str(row['user_id']),
                        first_name=row.get('first_name', ''),
                        last_name=row.get('last_name', ''),
                        job_description=row.get('job_description', ''),
                        status='Active'
                    )
                    db.session.add(user)
                else:
                    # Update existing user
                    user.first_name = row.get('first_name', user.first_name)
                    user.last_name = row.get('last_name', user.last_name)
                    user.job_description = row.get('job_description', user.job_description)
                    user.status = 'Active'
        
        # Process terminated employees
        if os.path.exists(terminated_csv_path):
            df_terminated = pd.read_csv(terminated_csv_path)
            
            for _, row in df_terminated.iterrows():
                user = User.query.filter_by(user_id=str(row['user_id'])).first()
                if user:
                    user.status = 'Terminated'
        
        db.session.commit()
        logging.info("Employee data synchronized successfully")
        
    except Exception as e:
        logging.error(f"Error syncing employee data: {str(e)}")

def process_terminated_employees():
    """Process terminated employees separately"""
    try:
        terminated_csv_path = get_setting('terminated_csv_path', '/tmp/terminated.csv')
        count = 0
        
        # Process terminated employees
        if os.path.exists(terminated_csv_path):
            df_terminated = pd.read_csv(terminated_csv_path)
            
            for _, row in df_terminated.iterrows():
                user = User.query.filter_by(user_id=str(row['user_id'])).first()
                if user and user.status != 'Terminated':
                    user.status = 'Terminated'
                    count += 1
            
            db.session.commit()
            logging.info(f"Processed {count} terminated employees")
        
        return count
        
    except Exception as e:
        logging.error(f"Error processing terminated employees: {str(e)}")
        return 0

def init_scheduler(app):
    """Initialize the scheduler"""
    scheduler = BackgroundScheduler()
    
    # Export CSV every 30 minutes
    scheduler.add_job(
        func=export_attendance_csv,
        trigger="interval",
        minutes=30,
        id='csv_export'
    )
    
    # Sync employee data daily at midnight
    scheduler.add_job(
        func=sync_employee_data,
        trigger="cron",
        hour=0,
        minute=0,
        id='employee_sync'
    )
    
    scheduler.start()
    logging.info("Scheduler initialized")
