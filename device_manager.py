import logging
from datetime import datetime
from app import db
from models import AttendanceLog, User, FingerTemplate, FaceTemplate

try:
    from zk import ZK
    ZK_AVAILABLE = True
except ImportError:
    ZK_AVAILABLE = False
    logging.warning("pyzk library not available. Device functionality will be limited.")

class DeviceManager:
    def __init__(self):
        self.connections = {}
    
    def connect_device(self, ip_address, port=4370, timeout=30):
        """Connect to ZKTeco device"""
        if not ZK_AVAILABLE:
            logging.error("ZK library not available")
            return None
            
        try:
            if ip_address in self.connections:
                return self.connections[ip_address]
            
            zk = ZK(ip_address, port=port, timeout=timeout)
            conn = zk.connect()
            self.connections[ip_address] = conn
            return conn
        except Exception as e:
            logging.error(f"Failed to connect to device {ip_address}: {str(e)}")
            return None
    
    def disconnect_device(self, ip_address):
        """Disconnect from ZKTeco device"""
        if ip_address in self.connections:
            try:
                self.connections[ip_address].disconnect()
                del self.connections[ip_address]
            except Exception as e:
                logging.error(f"Error disconnecting from {ip_address}: {str(e)}")
    
    def is_device_online(self, ip_address):
        """Check if device is online"""
        if not ZK_AVAILABLE:
            logging.debug(f"ZK library not available, simulating offline for {ip_address}")
            return False
            
        try:
            # Simple network connectivity check first
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((ip_address, 4370))
            sock.close()
            
            if result != 0:
                return False
                
            # If network check passes, try ZK connection
            conn = self.connect_device(ip_address)
            if conn:
                # Try to get device time to verify connection
                conn.get_time()
                return True
            return False
        except Exception as e:
            logging.debug(f"Device {ip_address} check failed: {str(e)}")
            return False
    
    def get_device_info(self, ip_address):
        """Get device information"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                return None
            
            info = {
                'serial_number': conn.get_serialnumber(),
                'version': conn.get_version(),
                'platform': conn.get_platform(),
                'device_name': conn.get_device_name(),
                'mac_address': conn.get_mac(),
                'time': conn.get_time(),
                'user_count': len(conn.get_users()),
                'template_count': len(conn.get_templates()),
                'face_count': len(conn.get_faces())
            }
            
            return info
        except Exception as e:
            logging.error(f"Error getting device info from {ip_address}: {str(e)}")
            return None
    
    def beep_device(self, ip_address):
        """Make device beep"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                return False
            
            # Enable/disable device to trigger beep
            conn.disable_device()
            conn.enable_device()
            return True
        except Exception as e:
            logging.error(f"Error beeping device {ip_address}: {str(e)}")
            return False
    
    def sync_attendance_logs(self, ip_address, device_id):
        """Sync attendance logs from device"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                return 0
            
            # Get attendance logs from device
            attendances = conn.get_attendance()
            new_logs_count = 0
            
            for att in attendances:
                # Check if log already exists
                existing_log = AttendanceLog.query.filter_by(
                    user_id=str(att.user_id),
                    timestamp=att.timestamp,
                    device_id=device_id
                ).first()
                
                if not existing_log:
                    log = AttendanceLog(
                        user_id=str(att.user_id),
                        device_id=device_id,
                        timestamp=att.timestamp,
                        status=self._get_status_text(att.status)
                    )
                    db.session.add(log)
                    new_logs_count += 1
            
            if new_logs_count > 0:
                db.session.commit()
                logging.info(f"Synced {new_logs_count} new logs from device {ip_address}")
            
            return new_logs_count
        except Exception as e:
            logging.error(f"Error syncing logs from {ip_address}: {str(e)}")
            return 0
    
    def sync_users_to_device(self, ip_address, area_id=None):
        """Sync users to device"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                return False
            
            # Clear existing users on device
            conn.clear_users()
            
            # Get users to sync (by area if specified)
            if area_id:
                users = User.query.filter_by(area_id=area_id, status='Active').all()
            else:
                users = User.query.filter_by(status='Active').all()
            
            for user in users:
                try:
                    # Set user on device
                    conn.set_user(
                        uid=int(user.user_id),
                        name=f"{user.first_name} {user.last_name}",
                        privilege=0,  # Normal user
                        password='',
                        group_id='',
                        user_id=user.user_id
                    )
                    
                    # Sync fingerprint templates
                    for finger in user.fingerprints:
                        conn.save_template(
                            user=int(user.user_id),
                            template=finger.template,
                            fid=finger.fid
                        )
                    
                    # Sync face templates
                    for face in user.faces:
                        conn.save_face(
                            user=int(user.user_id),
                            template=face.template
                        )
                        
                except Exception as e:
                    logging.error(f"Error syncing user {user.user_id} to device: {str(e)}")
                    continue
            
            return True
        except Exception as e:
            logging.error(f"Error syncing users to device {ip_address}: {str(e)}")
            return False
    
    def sync_time_to_device(self, ip_address):
        """Sync current time to device"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                return False
            
            conn.set_time(datetime.now())
            return True
        except Exception as e:
            logging.error(f"Error syncing time to device {ip_address}: {str(e)}")
            return False
    
    def _get_status_text(self, status_code):
        """Convert status code to text"""
        status_map = {
            0: 'Check In',
            1: 'Check Out',
            2: 'Break Out',
            3: 'Break In',
            4: 'OT In',
            5: 'OT Out'
        }
        return status_map.get(status_code, 'Unknown')
