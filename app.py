import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///attendance.db"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
socketio = SocketIO(app, cors_allowed_origins="*")

@login_manager.user_loader
def load_user(user_id):
    from models import AdminUser
    return AdminUser.query.get(int(user_id))

with app.app_context():
    # Import models and routes
    import models
    import routes
    import websocket_events
    
    # Create all tables
    db.create_all()
    
    # Create default admin user if it doesn't exist
    from models import AdminUser
    from werkzeug.security import generate_password_hash
    
    if not AdminUser.query.filter_by(username='admin').first():
        admin_user = AdminUser(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            force_change=True
        )
        db.session.add(admin_user)
        db.session.commit()
        logging.info("Default admin user created: admin/admin123")
    
    # Initialize scheduler
    from scheduler import init_scheduler
    init_scheduler(app)
    
    # Start device status monitoring (only if not in debug mode to avoid double start)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        from websocket_events import start_device_monitor
        start_device_monitor()
