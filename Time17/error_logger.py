import logging
import traceback
from datetime import datetime
from flask import request, has_request_context
from app import db
from models import ErrorLog

class DatabaseLogHandler(logging.Handler):
    """Custom logging handler to store errors in database"""
    
    def __init__(self):
        super().__init__()
        self.setLevel(logging.WARNING)  # Only capture WARNING and ERROR
        
    def emit(self, record):
        try:
            # Only log WARNING and ERROR levels
            if record.levelno < logging.WARNING:
                return
                
            # Get request context if available
            ip_address = None
            user_agent = None
            
            if has_request_context():
                try:
                    ip_address = request.remote_addr
                    user_agent = request.headers.get('User-Agent', '')[:256]
                except:
                    pass
            
            # Format the message
            message = self.format(record)
            
            # Get traceback if available
            traceback_str = None
            if record.exc_info:
                traceback_str = ''.join(traceback.format_exception(*record.exc_info))
            
            # Create error log entry
            error_log = ErrorLog(
                level=record.levelname,
                module=record.module if hasattr(record, 'module') else record.name,
                message=message,
                traceback=traceback_str,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Save to database
            db.session.add(error_log)
            db.session.commit()
            
        except Exception as e:
            # Don't let logging errors crash the application
            print(f"Error logging to database: {e}")

def setup_error_logging():
    """Setup database error logging"""
    try:
        # Get the root logger
        root_logger = logging.getLogger()
        
        # Check if handler already exists
        for handler in root_logger.handlers:
            if isinstance(handler, DatabaseLogHandler):
                return
        
        # Add database handler
        db_handler = DatabaseLogHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        db_handler.setFormatter(formatter)
        root_logger.addHandler(db_handler)
        
        print("Database error logging setup completed")
        
    except Exception as e:
        print(f"Error setting up database logging: {e}")

def log_error(message, level='ERROR', module='system', traceback_str=None):
    """Manually log an error to the database"""
    try:
        from app import app, db
        from models import ErrorLog
        from flask import request, has_request_context
        
        with app.app_context():
            error_log = ErrorLog(
                level=level,
                module=module,
                message=message,
                traceback=traceback_str,
                ip_address=request.remote_addr if has_request_context() and request else None,
                user_agent=request.headers.get('User-Agent') if has_request_context() and request else None
            )
            db.session.add(error_log)
            db.session.commit()
            print(f"Successfully logged {level} to database: {message}")
    except Exception as e:
        print(f"Failed to log error to database: {e}")
        # Fallback to file logging
        import logging
        logging.error(f"{module}: {message}")
        if traceback_str:
            logging.error(f"Traceback: {traceback_str}")

def cleanup_old_logs(days=30):
    """Clean up error logs older than specified days"""
    try:
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        deleted_count = ErrorLog.query.filter(ErrorLog.timestamp < cutoff_date).delete()
        db.session.commit()
        
        if deleted_count > 0:
            logging.info(f"Cleaned up {deleted_count} old error logs")
            
    except Exception as e:
        logging.error(f"Error cleaning up old logs: {e}")
