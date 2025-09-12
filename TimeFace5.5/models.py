from datetime import datetime
from app import db
from flask_login import UserMixin

class Area(db.Model):
    __tablename__ = 'areas'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

    devices = db.relationship('Device', backref='area_obj', lazy='dynamic')
    users = db.relationship('User', backref='area_obj', lazy='dynamic')

    def __repr__(self):
        return f"<Area {self.name}>"

class Device(db.Model):
    __tablename__ = 'devices'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128))
    ip_address = db.Column(db.String(64))
    mac_address = db.Column(db.String(64))
    serialnumber = db.Column(db.String(64))
    last_sync = db.Column(db.DateTime)
    online_status = db.Column(db.Boolean, default=False)

    area_id = db.Column(db.Integer, db.ForeignKey('areas.id'))

    def __repr__(self):
        return f"<Device {self.name} ({self.ip_address})>"

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), unique=True, nullable=False)
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    job_description = db.Column(db.String(128))
    status = db.Column(db.String(32), default='Active')  # Active/Terminated
    has_fingerprint = db.Column(db.Boolean, default=False)
    has_face = db.Column(db.Boolean, default=False)
    device_id = db.Column(db.String(64))
    site = db.Column(db.String(128))

    area_id = db.Column(db.Integer, db.ForeignKey('areas.id'))

    # Remove template storage - sync directly between devices
    logs = db.relationship('AttendanceLog', backref='user', lazy='dynamic')

    def __repr__(self):
        return f"<User {self.user_id} {self.first_name} {self.last_name}>"

class AttendanceLog(db.Model):
    __tablename__ = 'attendance_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), db.ForeignKey('users.user_id'), index=True)
    device_id = db.Column(db.String(64), index=True)
    area = db.Column(db.String(64), index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    status = db.Column(db.String(32))
    exported_flag = db.Column(db.Boolean, default=False, index=True)

    def __repr__(self):
        return f"<AttendanceLog {self.user_id} {self.timestamp}>"

class FingerTemplate(db.Model):
    __tablename__ = 'finger_templates'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), db.ForeignKey('users.user_id'), index=True)
    fid = db.Column(db.Integer)  # finger index 0-9
    template = db.Column(db.LargeBinary)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FaceTemplate(db.Model):
    __tablename__ = 'face_templates'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), db.ForeignKey('users.user_id'), index=True)
    template = db.Column(db.LargeBinary)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserImage(db.Model):
    __tablename__ = 'user_images'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), db.ForeignKey('users.user_id'), index=True)
    image = db.Column(db.LargeBinary)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AppSetting(db.Model):
    __tablename__ = 'app_settings'
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(256))

    def __repr__(self):
        return f"<AppSetting {self.key}={self.value}>"

class JobExecution(db.Model):
    __tablename__ = 'job_executions'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(64), nullable=False, index=True)
    job_name = db.Column(db.String(128))
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(32))  # 'running', 'completed', 'failed'
    result_data = db.Column(db.Text)  # JSON string with results
    error_message = db.Column(db.Text)
    
    def __repr__(self):
        return f"<JobExecution {self.job_id} {self.status}>"

class ErrorLog(db.Model):
    __tablename__ = 'error_logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    level = db.Column(db.String(16), index=True)  # ERROR, WARNING, INFO
    module = db.Column(db.String(64), index=True)
    message = db.Column(db.Text)
    traceback = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(256))
    
    def __repr__(self):
        return f"<ErrorLog {self.level} {self.timestamp}>"

class AdminUser(UserMixin, db.Model):
    __tablename__ = 'admin_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    force_change = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<AdminUser {self.username}>"
