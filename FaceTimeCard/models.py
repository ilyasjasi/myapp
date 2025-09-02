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

    area_id = db.Column(db.Integer, db.ForeignKey('areas.id'))

    finger_template = db.Column(db.LargeBinary)
    face_template = db.Column(db.LargeBinary)
    image = db.Column(db.LargeBinary)

    # relationships for templates
    fingerprints = db.relationship('FingerTemplate', backref='user', lazy='dynamic')
    faces = db.relationship('FaceTemplate', backref='user', lazy='dynamic')
    images = db.relationship('UserImage', backref='user', lazy='dynamic')

    logs = db.relationship('AttendanceLog', backref='user', lazy='dynamic')

    def __repr__(self):
        return f"<User {self.user_id} {self.first_name} {self.last_name}>"

class AttendanceLog(db.Model):
    __tablename__ = 'attendance_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), db.ForeignKey('users.user_id'))
    device_id = db.Column(db.String(64))
    area = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(32))
    exported_flag = db.Column(db.Boolean, default=False)

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

class AdminUser(UserMixin, db.Model):
    __tablename__ = 'admin_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    force_change = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<AdminUser {self.username}>"
