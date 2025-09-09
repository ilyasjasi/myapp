import logging
import socket
import time
from datetime import datetime, timedelta

try:
    from zk import ZK
    ZK_AVAILABLE = True
except ImportError:
    ZK_AVAILABLE = False
    logging.warning("pyzk library not available. Device functionality will be limited.")

class DeviceManager:
    def __init__(self):
        self.connections = {}
        self.connection_timeout = 10

    def connect_device(self, ip_address, timeout=10):
        """Connect to a ZKTeco device with enhanced connection handling
        
        Args:
            ip_address (str): IP address of the device
            timeout (int): Connection timeout in seconds (default: 10)
            
        Returns:
            ZK: Connected device object or None if connection failed
        """
        if not ZK_AVAILABLE:
            logging.error("pyzk library not available")
            return None
            
        # Check if we have a recent connection
        if ip_address in self.connections:
            conn, last_used = self.connections[ip_address]
            if (datetime.now() - last_used).total_seconds() < 30:
                try:
                    # Test if connection is still alive
                    conn.get_time()
                    self.connections[ip_address] = (conn, datetime.now())
                    logging.debug(f"Reusing existing connection to {ip_address}")
                    return conn
                except Exception as e:
                    logging.debug(f"Existing connection to {ip_address} is dead: {str(e)}")
                    try:
                        conn.disconnect()
                    except:
                        pass
                    del self.connections[ip_address]

        max_retries = 3
        retry_delay = 2
        
        for attempt in range(1, max_retries + 1):
            conn = None
            try:
                # First, check basic network connectivity
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((ip_address, 4370))
                sock.close()
            
                if result != 0:
                    logging.warning(f"TCP connection to {ip_address}:4370 failed (attempt {attempt}/{max_retries})")
                    time.sleep(retry_delay * attempt)
                    continue
                
                # Try different connection configurations
                configurations = [
                    # Config 1: Standard UDP with longer timeout
                    {"force_udp": True, "ommit_ping": True, "timeout": timeout, "verbose": False},
                    # Config 2: TCP mode with no ping
                    {"force_udp": False, "ommit_ping": True, "timeout": timeout, "verbose": False},
                    # Config 3: TCP with ping (some devices require this)
                    {"force_udp": False, "ommit_ping": False, "timeout": timeout, "verbose": False},
                ]
                
                for config_idx, config in enumerate(configurations):
                    try:
                        logging.debug(f"Trying configuration {config_idx + 1} for {ip_address}")
                        
                        conn = ZK(
                            ip_address,
                            port=4370,
                            password=0,
                            **config
                        )
                        
                        # Attempt connection
                        if conn.connect():
                            # Verify connection with a simple command
                            try:
                                conn.get_time()
                                # If successful, store connection
                                self.connections[ip_address] = (conn, datetime.now())
                                logging.info(f"Successfully connected to device {ip_address} using config {config_idx + 1}")
                                return conn
                            except Exception as verify_error:
                                logging.debug(f"Connection verification failed: {verify_error}")
                                conn.disconnect()
                                conn = None
                        else:
                            if conn:
                                try:
                                    conn.disconnect()
                                except:
                                    pass
                                conn = None
                            
                    except Exception as config_error:
                        logging.debug(f"Config {config_idx + 1} failed: {config_error}")
                        if conn:
                            try:
                                conn.disconnect()
                            except:
                                pass
                            conn = None
                        continue
                
                # If all configurations failed
                raise Exception("All connection configurations failed")
                
            except socket.timeout:
                logging.error(f"Connection to {ip_address} timed out (attempt {attempt}/{max_retries})")
            except ConnectionRefusedError:
                logging.error(f"Connection refused by device {ip_address} (attempt {attempt}/{max_retries})")
            except Exception as e:
                logging.error(f"Error connecting to {ip_address} (attempt {attempt}/{max_retries}): {str(e)}")
            
            # Clean up if connection was partially established
            if conn:
                try:
                    conn.disconnect()
                except:
                    pass
            
            # Exponential backoff before retry
            if attempt < max_retries:
                sleep_time = retry_delay * (2 ** (attempt - 1))
                logging.debug(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
        
        logging.error(f"Failed to connect to device {ip_address} after {max_retries} attempts")
        return None

    def is_device_online(self, ip_address, port=4370):
        """Check if device is online with improved connectivity test"""
        if not ZK_AVAILABLE:
            return False

        try:
            # Quick TCP check first
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((ip_address, port))
            sock.close()

            if result != 0:
                return False

            # Try simplified connection test
            try:
                # Use UDP with omit_ping for faster response
                conn = ZK(
                    ip_address,
                    port=port,
                    timeout=5,
                    password=0,
                    force_udp=True,
                    ommit_ping=True,
                    verbose=False
                )
                
                if conn.connect():
                    # Just check if we can connect, don't test commands
                    conn.disconnect()
                    return True
                return False
            except:
                # Try TCP as fallback
                try:
                    conn = ZK(
                        ip_address,
                        port=port,
                        timeout=5,
                        password=0,
                        force_udp=False,
                        ommit_ping=True,
                        verbose=False
                    )
                    
                    if conn.connect():
                        conn.disconnect()
                        return True
                except:
                    pass
            
            return False
            
        except Exception as e:
            logging.debug(f"Device {ip_address} check failed: {str(e)}")
            return False

    def get_device_info(self, ip_address, port=4370, timeout=10):
        """Fetch device information including employee count, biometric count, etc."""
        device_info = {
            'user_count': 0,
            'template_count': 0,
            'face_count': 0,
            'log_count': 0,
            'device_time': 'N/A',
            'serial': 'N/A',
            'today_logs': 0,
            'yesterday_logs': 0
        }

        conn = self.connect_device(ip_address, timeout)
        if not conn:
            return device_info

        try:
            # Get device time
            try:
                device_info['device_time'] = conn.get_time().strftime('%Y-%m-%d %H:%M:%S')
            except:
                device_info['device_time'] = 'N/A'

            # Get serial number
            try:
                device_info['serial'] = conn.get_serialnumber() or 'N/A'
            except:
                pass

            # Get user count
            try:
                users = conn.get_users()
                device_info['user_count'] = len(users) if users else 0
            except Exception as e:
                logging.warning(f"Error getting users from {ip_address}: {e}")
                device_info['user_count'] = 0

            # Get biometric counts
            try:
                device_info['template_count'] = getattr(conn, 'fingers', 0)
                device_info['face_count'] = getattr(conn, 'faces', 0)
            except Exception as e:
                logging.warning(f"Error getting biometric counts from {ip_address}: {e}")

            # Get attendance logs with date filtering
            try:
                today = datetime.now().date()
                yesterday = today - timedelta(days=1)
                
                # Try to get just the count if possible
                if hasattr(conn, 'get_attendance_size'):
                    device_info['log_count'] = conn.get_attendance_size()
                
                # Get today's and yesterday's logs with limit
                logs = conn.get_attendance()
                if logs:
                    device_info['log_count'] = len(logs)
                    device_info['today_logs'] = len([log for log in logs if hasattr(log, 'timestamp') and log.timestamp.date() == today])
                    device_info['yesterday_logs'] = len([log for log in logs if hasattr(log, 'timestamp') and log.timestamp.date() == yesterday])
                
            except Exception as e:
                if "10040" in str(e) or "buffer" in str(e).lower():
                    device_info['log_count'] = "Many"
                logging.warning(f"Error getting logs from {ip_address}: {e}")

            return device_info

        except Exception as e:
            logging.error(f"Error getting device info from {ip_address}: {str(e)}")
            return device_info
            
        finally:
            # Clean up connection
            try:
                conn.disconnect()
            except:
                pass
            if ip_address in self.connections:
                del self.connections[ip_address]

    def sync_users_between_devices(self, source_ip, target_ip):
        """Sync users from source device to target device"""
        try:
            source_conn = self.connect_device(source_ip)
            target_conn = self.connect_device(target_ip)
            
            if not source_conn or not target_conn:
                logging.error(f"Failed to connect to devices for sync: {source_ip} -> {target_ip}")
                return False
            
            # Get users from source device
            source_users = source_conn.get_users()
            target_users = target_conn.get_users()
            
            # Create set of existing user IDs on target
            target_user_ids = {user.user_id for user in target_users} if target_users else set()
            
            synced_count = 0
            for user in source_users:
                if user.user_id not in target_user_ids:
                    try:
                        # Add user to target device
                        target_conn.set_user(uid=user.uid, name=user.name, privilege=user.privilege, 
                                           password=user.password, group_id=user.group_id, user_id=user.user_id)
                        synced_count += 1
                        logging.info(f"Synced user {user.user_id} from {source_ip} to {target_ip}")
                    except Exception as e:
                        logging.warning(f"Failed to sync user {user.user_id}: {e}")
            
            source_conn.disconnect()
            target_conn.disconnect()
            
            logging.info(f"Synced {synced_count} users from {source_ip} to {target_ip}")
            return synced_count
            
        except Exception as e:
            logging.error(f"Error syncing users between devices: {e}")
            return False

    def sync_templates_between_devices(self, source_ip, target_ip):
        """Sync fingerprint and face templates from source device to target device"""
        try:
            source_conn = self.connect_device(source_ip)
            target_conn = self.connect_device(target_ip)
            
            if not source_conn or not target_conn:
                logging.error(f"Failed to connect to devices for template sync: {source_ip} -> {target_ip}")
                return False
            
            synced_count = 0
            
            # Sync fingerprint templates
            try:
                source_templates = source_conn.get_templates()
                target_templates = target_conn.get_templates()
                
                # Create set of existing template UIDs on target
                target_template_uids = {(tmpl.uid, tmpl.fid) for tmpl in target_templates} if target_templates else set()
                
                for template in source_templates:
                    if (template.uid, template.fid) not in target_template_uids:
                        try:
                            # Add fingerprint template to target device
                            target_conn.save_template(template)
                            synced_count += 1
                            logging.info(f"Synced fingerprint template UID:{template.uid} FID:{template.fid} from {source_ip} to {target_ip}")
                        except Exception as e:
                            logging.warning(f"Failed to sync fingerprint template UID:{template.uid} FID:{template.fid}: {e}")
            except Exception as e:
                logging.warning(f"Error syncing fingerprint templates: {e}")
            
            # Sync face templates (if supported)
            try:
                if hasattr(source_conn, 'get_face_templates') and hasattr(target_conn, 'save_face_template'):
                    source_faces = source_conn.get_face_templates()
                    target_faces = target_conn.get_face_templates() if hasattr(target_conn, 'get_face_templates') else []
                    
                    # Create set of existing face template UIDs on target
                    target_face_uids = {face.uid for face in target_faces} if target_faces else set()
                    
                    for face in source_faces:
                        if face.uid not in target_face_uids:
                            try:
                                # Add face template to target device (image data is stored in device)
                                target_conn.save_face_template(face)
                                synced_count += 1
                                logging.info(f"Synced face template UID:{face.uid} from {source_ip} to {target_ip}")
                            except Exception as e:
                                logging.warning(f"Failed to sync face template UID:{face.uid}: {e}")
                else:
                    logging.info("Face template sync not supported on one or both devices")
            except Exception as e:
                logging.warning(f"Error syncing face templates: {e}")
            
            # Sync user photos/images (if supported)
            try:
                if hasattr(source_conn, 'get_user_template') and hasattr(target_conn, 'set_user_template'):
                    source_users = source_conn.get_users()
                    for user in source_users[:10]:  # Limit to prevent timeout
                        try:
                            # Get user template data including any image data
                            user_template = source_conn.get_user_template(user.uid)
                            if user_template:
                                target_conn.set_user_template(user.uid, user_template)
                                logging.info(f"Synced user template data for UID:{user.uid}")
                        except Exception as e:
                            logging.warning(f"Failed to sync user template for UID:{user.uid}: {e}")
            except Exception as e:
                logging.warning(f"Error syncing user template data: {e}")
            
            source_conn.disconnect()
            target_conn.disconnect()
            
            logging.info(f"Synced {synced_count} templates total from {source_ip} to {target_ip}")
            return synced_count
            
        except Exception as e:
            logging.error(f"Error syncing templates between devices: {e}")
            return False

    def balance_devices_in_area(self, area_name=None):
        """Balance user and template distribution between devices in the same area"""
        try:
            import sqlite3
            conn = sqlite3.connect('instance/attendance.db')
            cursor = conn.cursor()
            
            # Get devices in the same area
            if area_name:
                cursor.execute("SELECT ip_address FROM devices WHERE area = ? AND online_status = 1", (area_name,))
            else:
                # Get all online devices if no area specified
                cursor.execute("SELECT ip_address FROM devices WHERE online_status = 1")
            
            device_ips = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            if len(device_ips) < 2:
                logging.info("Need at least 2 devices for balancing")
                return False
            
            # Get device info for all devices
            device_stats = []
            for ip in device_ips:
                info = self.get_device_info(ip)
                if info:
                    device_stats.append({
                        'ip': ip,
                        'user_count': info.get('user_count', 0),
                        'template_count': info.get('template_count', 0)
                    })
            
            if len(device_stats) < 2:
                logging.error("Could not get info from enough devices for balancing")
                return False
            
            # Sort devices by user count (descending)
            device_stats.sort(key=lambda x: x['user_count'], reverse=True)
            
            source_device = device_stats[0]  # Device with most users
            target_device = device_stats[-1]  # Device with least users
            
            user_diff = source_device['user_count'] - target_device['user_count']
            template_diff = source_device['template_count'] - target_device['template_count']
            
            logging.info(f"Balancing devices: {source_device['ip']} ({source_device['user_count']} users) -> {target_device['ip']} ({target_device['user_count']} users)")
            
            # Only balance if difference is significant (>100 users)
            if user_diff > 100:
                # Sync users from source to target
                synced_users = self.sync_users_between_devices(source_device['ip'], target_device['ip'])
                
                # Sync templates from source to target
                synced_templates = self.sync_templates_between_devices(source_device['ip'], target_device['ip'])
                
                logging.info(f"Balancing complete: {synced_users} users, {synced_templates} templates synced")
                return {'synced_users': synced_users, 'synced_templates': synced_templates}
            else:
                logging.info("Devices are already balanced")
                return {'synced_users': 0, 'synced_templates': 0}
                
        except Exception as e:
            logging.error(f"Error balancing devices: {e}")
            return False

    def collect_logs_from_device(self, ip_address):
        """Collect attendance logs from a specific device and store in database"""
        try:
            conn = self.connect_device(ip_address, timeout=10)
            if not conn:
                return 0
            
            # Get attendance logs from device
            logs = conn.get_attendance()
            if not logs:
                conn.disconnect()
                return 0
            
            # Store logs in database
            import sqlite3
            db_conn = sqlite3.connect('instance/attendance.db')
            cursor = db_conn.cursor()
            
            # Get device information (device_id, area)
            cursor.execute('SELECT device_id, d.name, a.name FROM devices d LEFT JOIN areas a ON d.area_id = a.id WHERE d.ip_address = ?', (ip_address,))
            device_row = cursor.fetchone()
            if not device_row:
                logging.warning(f"Device {ip_address} not found in database")
                db_conn.close()
                conn.disconnect()
                return 0
            
            device_id, device_name, area_name = device_row
            area_name = area_name or 'Unknown'
            logs_inserted = 0
            
            for log in logs:
                try:
                    # Check if log already exists
                    cursor.execute("""
                        SELECT id FROM attendance_logs 
                        WHERE device_id = ? AND user_id = ? AND timestamp = ?
                    """, (device_id, log.user_id, log.timestamp.isoformat() if hasattr(log, 'timestamp') else None))
                    
                    if not cursor.fetchone():
                        # Insert new log with correct device_id and area information
                        cursor.execute("""
                            INSERT INTO attendance_logs (device_id, user_id, timestamp, status, area, exported_flag)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            device_id,
                            log.user_id,
                            log.timestamp.isoformat() if hasattr(log, 'timestamp') else datetime.now().isoformat(),
                            'Check In' if getattr(log, 'punch', 0) == 0 else 'Check Out',
                            area_name,
                            0  # Not exported yet
                        ))
                        logs_inserted += 1
                        
                except Exception as e:
                    logging.warning(f"Failed to insert log for user {getattr(log, 'user_id', 'unknown')}: {e}")
                    continue
            
            db_conn.commit()
            db_conn.close()
            conn.disconnect()
            
            logging.info(f"Collected {logs_inserted} new logs from device {ip_address}")
            return logs_inserted
            
        except Exception as e:
            logging.error(f"Error collecting logs from device {ip_address}: {e}")
            return 0

    def set_device_time(self, ip_address, datetime_obj=None):
        """Set device time"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                return False

            if datetime_obj is None:
                datetime_obj = datetime.now()

            conn.set_time(datetime_obj)
            return True
        except Exception as e:
            logging.error(f"Error setting time for device {ip_address}: {str(e)}")
            return False

    def beep_device(self, ip_address):
        """Make device beep"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                return False

            conn.test_voice()
            return True
        except Exception as e:
            logging.error(f"Error beeping device {ip_address}: {str(e)}")
            return False

    def sync_attendance_logs(self, ip_address, device_id, auto_fetch=True):
        """Sync attendance logs from device - scheduler-compatible version using direct SQLite"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                return 0

            attendances = conn.get_attendance()
            if not attendances:
                conn.disconnect()
                return 0

            # Use direct SQLite connection for scheduler compatibility
            import sqlite3
            db_conn = sqlite3.connect('instance/attendance.db')
            cursor = db_conn.cursor()
            
            # Get device information (device_id should be the actual device_id, not database id)
            cursor.execute('SELECT device_id, d.name, a.name FROM devices d LEFT JOIN areas a ON d.area_id = a.id WHERE d.id = ?', (device_id,))
            device_info = cursor.fetchone()
            if device_info:
                actual_device_id, device_name, area_name = device_info
                area_name = area_name or 'Unknown'
            else:
                actual_device_id = device_id
                area_name = 'Unknown'

            new_logs_count = 0

            for att in attendances:
                try:
                    # Get user_id using correct attribute
                    user_id = getattr(att, 'user_id', None) or getattr(att, 'uid', None)
                    if not user_id:
                        continue

                    user_id_str = str(user_id)
                    timestamp = getattr(att, 'timestamp', None)
                    status = getattr(att, 'status', None) or getattr(att, 'punch', None)

                    if not timestamp:
                        continue

                    # Check if log already exists
                    cursor.execute("""
                        SELECT id FROM attendance_logs 
                        WHERE device_id = ? AND user_id = ? AND timestamp = ?
                    """, (actual_device_id, user_id_str, timestamp.isoformat()))

                    if not cursor.fetchone():
                        # Insert new log with correct device_id and area information
                        cursor.execute("""
                            INSERT INTO attendance_logs (device_id, user_id, timestamp, status, area, exported_flag)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            actual_device_id,
                            user_id_str,
                            timestamp.isoformat(),
                            'Check In' if status == 0 else 'Check Out',
                            area_name,
                            0  # Not exported yet
                        ))
                        new_logs_count += 1

                except Exception as e:
                    logging.warning(f"Failed to insert log for user {getattr(att, 'user_id', 'unknown')}: {e}")
                    continue

            if new_logs_count > 0:
                db_conn.commit()
                logging.info(f"Synced {new_logs_count} new logs from device {ip_address}")

            db_conn.close()
            conn.disconnect()
            return new_logs_count
            
        except Exception as e:
            logging.error(f"Error syncing logs from {ip_address}: {str(e)}")
            return 0

    def sync_users_from_device(self, ip_address, device_id, area_id=None):
        """Sync users from device to database with auto-fetch logs - using user_id not uid"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                logging.error(f"Could not connect to device {ip_address}")
                return 0

            device_users = conn.get_users() or []
            templates = conn.get_templates() or []

            if not device_users:
                logging.warning(f"No users found on device {ip_address}")
                return 0

            # Create lookup dictionaries for templates using both user_id and uid
            template_dict = {}
            face_dict = {}
            
            # Get fingerprint templates - check by both user_id and uid
            for t in templates:
                # Try user_id first, then fall back to uid
                user_id = getattr(t, 'user_id', None) or getattr(t, 'uid', None)
                if user_id:
                    template_dict[str(user_id)] = True

            # Check for fingerprint templates by iterating through users and checking templates
            for user in device_users:
                try:
                    uid = getattr(user, 'uid', None)
                    user_id = getattr(user, 'user_id', None)
                    
                    if uid:
                        # Check if user has fingerprint template
                        try:
                            finger_templates = conn.get_user_template(uid=uid)
                            if finger_templates:
                                if user_id:
                                    template_dict[str(user_id)] = True
                                template_dict[str(uid)] = True
                        except:
                            pass
                        
                        # Check if user has face template
                        try:
                            face_template = conn.get_face_template(uid=uid)
                            if face_template:
                                if user_id:
                                    face_dict[str(user_id)] = True
                                face_dict[str(uid)] = True
                        except:
                            pass
                except:
                    continue

            # Additional face template detection
            try:
                faces = conn.get_faces() if hasattr(conn, 'get_faces') else []
                for f in faces:
                    user_id = getattr(f, 'user_id', None) or getattr(f, 'uid', None)
                    if user_id:
                        face_dict[str(user_id)] = True
            except:
                pass

            # Use direct SQLite connection for scheduler compatibility
            import sqlite3
            db_conn = sqlite3.connect('instance/attendance.db')
            cursor = db_conn.cursor()
            
            # Get device info
            cursor.execute('SELECT d.name, a.name FROM devices d LEFT JOIN areas a ON d.area_id = a.id WHERE d.id = ?', (device_id,))
            device_info = cursor.fetchone()
            device_name = device_info[0] if device_info else 'Unknown'

            synced_count = 0
            updated_count = 0

            for device_user in device_users:
                try:
                    # Use user_id attribute instead of uid
                    user_id = getattr(device_user, 'user_id', None)
                    if not user_id:
                        continue

                    user_id_str = str(user_id)
                    
                    # Check if user exists
                    cursor.execute('SELECT id, area_id, device_id, site, has_fingerprint, has_face FROM users WHERE user_id = ?', (user_id_str,))
                    existing_user = cursor.fetchone()

                    user_name = getattr(device_user, 'name', f'User{user_id_str}') or f'User{user_id_str}'
                    name_parts = user_name.split()
                    first_name = name_parts[0] if name_parts else f'User{user_id_str}'
                    last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

                    has_fingerprint = 1 if user_id_str in template_dict else 0
                    has_face = 1 if user_id_str in face_dict else 0

                    if not existing_user:
                        # Create new user
                        cursor.execute("""
                            INSERT INTO users (user_id, first_name, last_name, status, area_id, device_id, site, has_fingerprint, has_face)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            user_id_str,
                            first_name,
                            last_name,
                            'Active',
                            area_id,
                            device_id,
                            device_name,
                            has_fingerprint,
                            has_face
                        ))
                        synced_count += 1
                    else:
                        # Update existing user with device info
                        updated = False
                        updates = []
                        values = []
                        
                        if not existing_user[1] and area_id:  # area_id
                            updates.append('area_id = ?')
                            values.append(area_id)
                            updated = True
                        if not existing_user[2]:  # device_id
                            updates.append('device_id = ?')
                            values.append(device_id)
                            updated = True
                        if not existing_user[3]:  # site
                            updates.append('site = ?')
                            values.append(device_name)
                            updated = True
                        if existing_user[4] != has_fingerprint:  # has_fingerprint
                            updates.append('has_fingerprint = ?')
                            values.append(has_fingerprint)
                            updated = True
                        if existing_user[5] != has_face:  # has_face
                            updates.append('has_face = ?')
                            values.append(has_face)
                            updated = True

                        if updated:
                            values.append(user_id_str)
                            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", values)
                            updated_count += 1

                except Exception as e:
                    logging.error(f"Error processing user {getattr(device_user, 'user_id', 'unknown')}: {e}")
                    continue

            if synced_count > 0 or updated_count > 0:
                db_conn.commit()
                logging.info(f"Synced {synced_count} new users and updated {updated_count} users from device {ip_address}")

            db_conn.close()
            
            # Note: Log collection is handled by separate auto_log_collection_job
            # No need to auto-fetch logs here to avoid duplication

            return synced_count
        except Exception as e:
            logging.error(f"Error syncing users from device {ip_address}: {str(e)}")
            return 0

    def get_next_available_uid(self, ip_address):
        """Get next available UID for device"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                return 1

            device_users = conn.get_users() or []
            if not device_users:
                return 1
            
            # Get max UID from device users
            max_uid = 0
            for user in device_users:
                uid = getattr(user, 'uid', 0)
                if uid > max_uid:
                    max_uid = uid
            
            return max_uid + 1
        except Exception as e:
            logging.error(f"Error getting next UID for {ip_address}: {str(e)}")
            return 1

    def sync_users_to_device(self, ip_address, area_id=None):
        """Sync users to device with proper UID assignment"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                return False

            if area_id:
                users = User.query.filter_by(area_id=area_id, status='Active').all()
            else:
                users = User.query.filter_by(status='Active').all()

            # Get existing device users to check for conflicts
            device_users = conn.get_users() or []
            existing_user_ids = {getattr(u, 'user_id', '') for u in device_users}
            
            # Get next available UID
            next_uid = self.get_next_available_uid(ip_address)

            for user in users:
                try:
                    # Skip if user already exists on device
                    if user.user_id in existing_user_ids:
                        continue
                        
                    conn.set_user(
                        uid=next_uid,
                        name=f"{user.first_name} {user.last_name}".strip(),
                        privilege=0,
                        password='',
                        group_id='',
                        user_id=user.user_id
                    )
                    next_uid += 1
                    logging.info(f"Added user {user.user_id} to device {ip_address}")
                except Exception as e:
                    logging.error(f"Error syncing user {user.user_id} to device: {str(e)}")
                    continue

            return True
        except Exception as e:
            logging.error(f"Error syncing users to device {ip_address}: {str(e)}")
            return False

    def sync_time_to_device(self, ip_address):
        """Sync current time to device"""
        return self.set_device_time(ip_address, datetime.now())

    def sync_devices_in_area(self, area_id):
        """Comprehensive sync of users and templates between devices in same area"""
        try:
            devices = Device.query.filter_by(area_id=area_id, online_status=True).all()
            if len(devices) < 2:
                return True

            print(f"Syncing {len(devices)} devices in area {area_id}...")
            
            # Step 1: Collect all data from all devices
            all_device_data = {}
            
            for device in devices:
                try:
                    conn = self.connect_device(device.ip_address)
                    if not conn:
                        continue
                        
                    employees = conn.get_users() or []
                    templates = {}
                    
                    # Get templates for each employee
                    for emp in employees:
                        try:
                            user_template = conn.get_user_template(uid=emp.uid)
                            if user_template:
                                templates[emp.user_id] = user_template
                        except:
                            pass
                    
                    all_device_data[device.ip_address] = {
                        'employees': {emp.user_id: emp for emp in employees},
                        'templates': templates,
                        'device': device
                    }
                    
                    print(f"Device {device.ip_address} has {len(employees)} employees, {len(templates)} templates")
                    
                except Exception as e:
                    logging.error(f"Error collecting data from device {device.ip_address}: {e}")
                    continue

            # Step 2: Sync data between devices
            for source_ip, source_data in all_device_data.items():
                for target_ip, target_data in all_device_data.items():
                    if source_ip == target_ip:
                        continue
                        
                    try:
                        self._sync_between_two_devices(source_data, target_data, source_ip, target_ip)
                    except Exception as e:
                        logging.error(f"Error syncing from {source_ip} to {target_ip}: {e}")
                        continue

            return True
            
        except Exception as e:
            logging.error(f"Error syncing devices in area: {str(e)}")
            return False

    def _sync_between_two_devices(self, source_data, target_data, source_ip, target_ip):
        """Sync data between two specific devices"""
        source_employees = source_data['employees']
        target_employees = target_data['employees']
        source_templates = source_data['templates']
        
        target_conn = self.connect_device(target_ip)
        if not target_conn:
            return False
            
        # Find users missing on target device
        users_to_add = [emp for user_id, emp in source_employees.items() 
                       if user_id not in target_employees]
        
        if users_to_add:
            print(f"Adding {len(users_to_add)} users from {source_ip} to {target_ip}")
            
            # Get max UID on target device
            existing_uids = {emp.uid for emp in target_employees.values()}
            max_uid = max(existing_uids) if existing_uids else 0
            
            for employee in users_to_add:
                try:
                    new_uid = max_uid + 1
                    max_uid += 1
                    
                    # Add user to target device
                    target_conn.set_user(
                        uid=new_uid,
                        name=employee.name,
                        privilege=employee.privilege,
                        password=employee.password,
                        user_id=employee.user_id,
                    )
                    
                    # Add fingerprint template if exists
                    if employee.user_id in source_templates:
                        try:
                            target_conn.save_user_template(
                                user=new_uid,
                                fingers=source_templates[employee.user_id]
                            )
                            print(f"Synced fingerprint for user {employee.user_id} to {target_ip}")
                        except Exception as e:
                            logging.error(f"Error syncing template: {e}")
                    
                    print(f"Added user {employee.user_id} to {target_ip} with UID {new_uid}")
                    
                except Exception as e:
                    logging.error(f"Error adding user {employee.user_id} to {target_ip}: {e}")
        
        # Update templates for existing users who don't have them
        target_templates = target_data['templates']
        for user_id, template in source_templates.items():
            if user_id in target_employees and user_id not in target_templates:
                try:
                    target_uid = target_employees[user_id].uid
                    target_conn.save_user_template(user=target_uid, fingers=template)
                    print(f"Updated template for existing user {user_id} on {target_ip}")
                except Exception as e:
                    logging.error(f"Error updating template for {user_id}: {e}")

    def sync_templates_between_area_devices(self, area_id):
        """Smart sync templates between area devices with queue management and crash prevention"""
        try:
            # Check if sync is already in progress for this area
            sync_key = f"area_sync_{area_id}"
            if hasattr(self, '_sync_queue') and sync_key in self._sync_queue:
                logging.info(f"Sync already in progress for area {area_id}, skipping")
                return 0
            
            # Initialize sync queue if not exists
            if not hasattr(self, '_sync_queue'):
                self._sync_queue = set()
            
            # Add to sync queue
            self._sync_queue.add(sync_key)
            
            try:
                devices = Device.query.filter_by(area_id=area_id, online_status=True).all()
                if len(devices) < 2:
                    return 0

                # Limit to maximum 5 devices to prevent crashes
                if len(devices) > 5:
                    logging.warning(f"Area {area_id} has {len(devices)} devices, limiting to 5 to prevent crashes")
                    devices = devices[:5]

                # Find device with most users and templates (master device)
                device_stats = []
                for device in devices:
                    try:
                        # Use shorter timeout to prevent hanging
                        conn = self.connect_device(device.ip_address, timeout=5)
                        if conn:
                            users = conn.get_users()
                            user_count = len(users) if users else 0
                            
                            # Skip template counting if too many users (prevents buffer overflow)
                            template_count = 0
                            if user_count < 500:  # Only count templates for smaller devices
                                try:
                                    all_templates = conn.get_templates()
                                    template_count = len(all_templates) if all_templates else 0
                                except Exception as e:
                                    logging.warning(f"Could not count templates for device {device.ip_address}: {e}")
                                    template_count = 0
                            
                            device_stats.append({
                                'device': device,
                                'user_count': user_count,
                                'template_count': template_count,
                                'total_score': user_count + template_count
                            })
                            self.disconnect_device(device.ip_address)
                    except Exception as e:
                        logging.error(f"Error getting stats for device {device.ip_address}: {e}")
                        continue

                if not device_stats:
                    return 0

                # Sort by total score to find master device
                device_stats.sort(key=lambda x: x['total_score'], reverse=True)
                master_device = device_stats[0]['device']
                
                logging.info(f"Using device {master_device.ip_address} as master for area {area_id} (Users: {device_stats[0]['user_count']}, Templates: {device_stats[0]['template_count']})")

                # Get all users from master device with timeout protection
                master_conn = self.connect_device(master_device.ip_address, timeout=10)
                if not master_conn:
                    return 0

                try:
                    master_users = master_conn.get_users()
                    if not master_users:
                        self.disconnect_device(master_device.ip_address)
                        return 0
                        
                    # Limit users to prevent crashes
                    if len(master_users) > 200:
                        logging.warning(f"Master device has {len(master_users)} users, limiting to 200 to prevent crashes")
                        master_users = master_users[:200]
                        
                except Exception as e:
                    logging.error(f"Error getting users from master device: {e}")
                    self.disconnect_device(master_device.ip_address)
                    return 0

                synced_count = 0
                batch_size = 10  # Smaller batches to prevent timeout
                max_sync_time = 300  # 5 minutes maximum sync time
                import time
                start_time = time.time()

                # Sync to all other devices in area
                for target_stat in device_stats[1:]:
                    # Check if we've exceeded maximum sync time
                    if time.time() - start_time > max_sync_time:
                        logging.warning(f"Sync timeout reached, stopping sync for area {area_id}")
                        break
                        
                    target_device = target_stat['device']
                    logging.info(f"Syncing from master to device {target_device.ip_address}")
                    
                    try:
                        target_conn = self.connect_device(target_device.ip_address, timeout=10)
                        if not target_conn:
                            continue

                        target_users = target_conn.get_users()
                        target_user_ids = {u.user_id for u in target_users} if target_users else set()

                        # Process users in small batches with timeout checks
                        for i in range(0, len(master_users), batch_size):
                            # Check timeout again
                            if time.time() - start_time > max_sync_time:
                                break
                                
                            batch_users = master_users[i:i + batch_size]
                            
                            for master_user in batch_users:
                                try:
                                    # Only sync templates for users that exist on both devices
                                    if master_user.user_id in target_user_ids:
                                        try:
                                            master_templates = master_conn.get_user_template(uid=master_user.uid)
                                            if master_templates:
                                                # Find corresponding user on target device
                                                target_user = next((u for u in target_users if u.user_id == master_user.user_id), None)
                                                if target_user:
                                                    # Check if target user already has templates
                                                    try:
                                                        existing_templates = target_conn.get_user_template(uid=target_user.uid)
                                                        if not existing_templates:  # Only sync if no templates exist
                                                            target_conn.save_user_template(user=target_user, fingers=master_templates)
                                                            synced_count += 1
                                                            logging.info(f"Synced templates for user {master_user.user_id}")
                                                    except:
                                                        # If can't check existing templates, try to sync anyway
                                                        target_conn.save_user_template(user=target_user, fingers=master_templates)
                                                        synced_count += 1
                                        except Exception as e:
                                            logging.error(f"Error syncing template for user {master_user.user_id}: {e}")
                                            continue

                                except Exception as e:
                                    logging.error(f"Error processing user {master_user.user_id}: {e}")
                                    continue
                            
                            # Longer delay between batches to prevent device overload
                            time.sleep(0.5)

                        self.disconnect_device(target_device.ip_address)
                    except Exception as e:
                        logging.error(f"Error syncing to device {target_device.ip_address}: {e}")
                        continue

                self.disconnect_device(master_device.ip_address)
                logging.info(f"Smart synced {synced_count} templates from master device to {len(device_stats)-1} devices in area {area_id}")
                return synced_count
                
            finally:
                # Remove from sync queue
                self._sync_queue.discard(sync_key)

        except Exception as e:
            logging.error(f"Error in smart template sync for area {area_id}: {e}")
            return 0

    def sync_templates_between_devices(self, area_id):
        """Sync biometric templates between devices in same area"""
        return self.sync_devices_in_area(area_id)

    def push_users_to_device(self, target_ip, area_id):
        """Push all users from database to a specific device in the area"""
        try:
            conn = self.connect_device(target_ip)
            if not conn:
                logging.error(f"Cannot connect to device {target_ip}")
                return False

            # Get all active users in the same area
            users = User.query.filter_by(area_id=area_id, status='Active').all()
            
            pushed_count = 0
            for user in users:
                try:
                    # Create user on device - handle large user IDs
                    uid = int(user.user_id)
                    if uid > 65535:
                        uid = uid % 65536  # Wrap around for large IDs
                    
                    conn.set_user(
                        uid=uid,
                        name=f"{user.first_name} {user.last_name}",
                        privilege=0,  # Regular user
                        password='',
                        group_id='',
                        user_id=str(user.user_id)
                    )
                    pushed_count += 1
                except Exception as e:
                    logging.error(f"Error pushing user {user.user_id} to device {target_ip}: {e}")
                    continue

            self.disconnect_device(target_ip)
            logging.info(f"Pushed {pushed_count} users to device {target_ip}")
            return True

        except Exception as e:
            logging.error(f"Error pushing users to device {target_ip}: {e}")
            return False

    def push_single_user_to_device(self, target_ip, user_id):
        """Push a specific user to device with update/create logic"""
        try:
            conn = self.connect_device(target_ip)
            if not conn:
                logging.error(f"Cannot connect to device {target_ip}")
                return False

            # Get the specific user
            user = User.query.filter_by(user_id=user_id, status='Active').first()
            if not user:
                logging.error(f"User {user_id} not found or not active")
                return False
            
            # Check if user already exists on device
            device_users = conn.get_users()
            existing_user = None
            
            uid = int(user.user_id)
            if uid > 65535:
                uid = uid % 65536  # Wrap around for large IDs
            
            for device_user in device_users:
                if device_user.user_id == str(user.user_id) or device_user.uid == uid:
                    existing_user = device_user
                    break
            
            try:
                if existing_user:
                    # User already exists - skip to avoid "Can't set user" error
                    logging.info(f"User {user.user_id} already exists on device {target_ip} - skipping user creation")
                else:
                    # Create new user only if not exists
                    conn.set_user(
                        uid=uid,
                        name=f"{user.first_name} {user.last_name}",
                        privilege=0,
                        password='',
                        group_id='',
                        user_id=str(user.user_id)
                    )
                    logging.info(f"Created user {user.user_id} on device {target_ip}")
                
                self.disconnect_device(target_ip)
                return True
                
            except Exception as e:
                logging.error(f"Error setting user {user.user_id} on device {target_ip}: {e}")
                self.disconnect_device(target_ip)
                return False

        except Exception as e:
            logging.error(f"Error pushing user {user_id} to device {target_ip}: {e}")
            return False

    def push_templates_to_device(self, target_ip, area_id):
        """Push all biometric templates from database to a specific device"""
        try:
            conn = self.connect_device(target_ip)
            if not conn:
                logging.error(f"Cannot connect to device {target_ip}")
                return False

            # Get all finger templates for users in this area
            finger_templates = db.session.query(FingerTemplate).join(User).filter(
                User.area_id == area_id,
                User.status == 'Active'
            ).all()

            # Get all face templates for users in this area  
            face_templates = db.session.query(FaceTemplate).join(User).filter(
                User.area_id == area_id,
                User.status == 'Active'
            ).all()

            pushed_count = 0
            
            # Templates are not stored in DB - only synced between devices
            # This function now only handles device-to-device template sync
            logging.info(f"Template sync handled by sync_templates_between_area_devices for device {target_ip}")

            self.disconnect_device(target_ip)
            logging.info(f"Pushed {pushed_count} templates to device {target_ip}")
            return True

        except Exception as e:
            logging.error(f"Error pushing templates to device {target_ip}: {e}")
            return False

    def push_user_templates_to_device(self, target_ip, user_id):
        """Push specific user's biometric templates to device from other devices in same area"""
        try:
            user = User.query.filter_by(user_id=user_id, status='Active').first()
            if not user or not user.area_id:
                logging.error(f"User {user_id} not found, not active, or no area assigned")
                return False

            # Get all devices in the same area
            area_devices = Device.query.filter_by(area_id=user.area_id, online_status=True).all()
            if len(area_devices) < 2:
                logging.info(f"Only one device in area {user.area_id}, no template sync needed")
                return True

            target_conn = self.connect_device(target_ip)
            if not target_conn:
                logging.error(f"Cannot connect to target device {target_ip}")
                return False

            # Find user on target device
            target_users = target_conn.get_users()
            target_user = None
            for device_user in target_users:
                if str(device_user.user_id) == str(user_id):
                    target_user = device_user
                    break

            if not target_user:
                logging.error(f"User {user_id} not found on target device {target_ip}")
                self.disconnect_device(target_ip)
                return False

            # Check if user already has templates on target device
            try:
                existing_templates = target_conn.get_user_template(uid=target_user.uid)
                if existing_templates:
                    logging.info(f"User {user_id} already has templates on device {target_ip}")
                    self.disconnect_device(target_ip)
                    return True
            except:
                pass

            # Find templates from other devices in the area
            templates_found = False
            for source_device in area_devices:
                if source_device.ip_address == target_ip:
                    continue

                try:
                    source_conn = self.connect_device(source_device.ip_address)
                    if not source_conn:
                        continue

                    source_users = source_conn.get_users()
                    source_user = None
                    for device_user in source_users:
                        if str(device_user.user_id) == str(user_id):
                            source_user = device_user
                            break

                    if source_user:
                        # Get templates from source device
                        try:
                            user_templates = source_conn.get_user_template(uid=source_user.uid)
                            if user_templates:
                                # Push templates to target device
                                target_conn.save_user_template(user=target_user, fingers=user_templates)
                                templates_found = True
                                logging.info(f"Successfully synced templates for user {user_id} from {source_device.ip_address} to {target_ip}")
                                self.disconnect_device(source_device.ip_address)
                                break
                        except Exception as e:
                            logging.error(f"Error syncing templates for user {user_id}: {e}")

                    self.disconnect_device(source_device.ip_address)
                except Exception as e:
                    logging.error(f"Error connecting to source device {source_device.ip_address}: {e}")
                    continue

            self.disconnect_device(target_ip)
            
            if templates_found:
                logging.info(f"Successfully pushed templates for user {user_id} to device {target_ip}")
                return True
            else:
                logging.warning(f"No templates found for user {user_id} in area devices")
                return False

        except Exception as e:
            logging.error(f"Error pushing user {user_id} templates to device {target_ip}: {e}")
            return False

    def remove_terminated_users_from_device(self, ip_address):
        """Remove terminated users from device - enhanced version"""
        try:
            conn = self.connect_device(ip_address)
            if not conn:
                logging.error(f"Could not connect to device {ip_address}")
                return 0

            # Get all users from device
            device_users = conn.get_users()
            if not device_users:
                logging.info(f"No users found on device {ip_address}")
                self.disconnect_device(ip_address)
                return 0

            # Get terminated users from database
            terminated_users = User.query.filter_by(status='Terminated').all()
            terminated_user_ids = {user.user_id for user in terminated_users}
            
            if not terminated_user_ids:
                logging.info(f"No terminated users in database")
                self.disconnect_device(ip_address)
                return 0

            logging.info(f"Found {len(terminated_user_ids)} terminated users in database")
            logging.info(f"Found {len(device_users)} users on device {ip_address}")

            removed_count = 0
            for device_user in device_users:
                try:
                    # Check if device user is terminated in database
                    if str(device_user.user_id) in terminated_user_ids:
                        logging.info(f"Attempting to delete terminated user {device_user.user_id} (UID: {device_user.uid}) from device {ip_address}")
                        
                        # Try to delete user from device
                        result = conn.delete_user(uid=device_user.uid)
                        if result:
                            removed_count += 1
                            logging.info(f"Successfully removed terminated user {device_user.user_id} from device {ip_address}")
                        else:
                            logging.warning(f"Failed to remove user {device_user.user_id} from device {ip_address}")
                    
                except Exception as e:
                    logging.error(f"Error removing user {device_user.user_id} from device {ip_address}: {e}")
                    continue

            # Verify removal by checking users again
            updated_users = conn.get_users()
            remaining_terminated = [u for u in updated_users if str(u.user_id) in terminated_user_ids]
            
            if remaining_terminated:
                logging.warning(f"Still {len(remaining_terminated)} terminated users remain on device {ip_address}")
                for user in remaining_terminated:
                    logging.warning(f"Terminated user still on device: {user.user_id}")

            self.disconnect_device(ip_address)
            logging.info(f"Removed {removed_count} terminated users from device {ip_address}")
            return removed_count

        except Exception as e:
            logging.error(f"Error removing terminated users from device {ip_address}: {e}")
            return 0

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

    def get_device_data(self, ip, port=4370, timeout=3):
        """Get device statistics and information - using proper ZK attributes"""
        data = {
            'serial': "N/A",
            'area': "N/A",
            'employee_count': 0,
            'fingerprint_count': 0,
            'face_count': 0,
            'total_logs': 0,
            'yesterday_logs': 0,
            'today_logs': 0,
        }

        try:
            if not ZK_AVAILABLE:
                return data

            zk_instance = ZK(ip, port=port, timeout=timeout)
            conn = zk_instance.connect()

            if conn:  # Check to ensure connection is established
                data['serial'] = conn.get_serialnumber()

                # Use minimal data retrieval
                users = conn.get_users()
                data['employee_count'] = len(users) if users else 0
                data['fingerprint_count'] = getattr(conn, 'fingers', 0)
                data['face_count'] = getattr(conn, 'faces', 0)

                # Add back the attendance logs counting
                logs = conn.get_attendance()
                from datetime import datetime, timedelta
                today = datetime.now().date()
                yesterday = today - timedelta(days=1)
                data['total_logs'] = len(logs) if logs else 0
                data['yesterday_logs'] = len([log for log in logs if log.timestamp.date() == yesterday]) if logs else 0
                data['today_logs'] = len([log for log in logs if log.timestamp.date() == today]) if logs else 0

                conn.disconnect()

        except Exception as e:
            logging.error(f"Failed to retrieve data for {ip}: {e}")

        return data