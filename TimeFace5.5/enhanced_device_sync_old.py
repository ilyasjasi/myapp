#!/usr/bin/env python3
"""
Enhanced Device Sync Module for ZKTeco Devices
COMPLETE SOLUTION: Users, Fingerprints, Face Templates, and Photos
Uses hybrid approach: pyzk (users/fingerprints) + fpmachine (faces/photos)
"""

import logging
import time
import threading
import os
import glob
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from zk import ZK

# Import database models for user validation
try:
    from models import User, Device, Area
    from app import db
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    logging.warning("Database models not available - user validation disabled")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('device_sync.log'),
        logging.StreamHandler()
    ]
)

class EnhancedDeviceSync:
    """Enhanced sync for ZKTeco devices with COMPLETE face template and photo support"""
    
    def __init__(self):
        self.sync_in_progress = set()
        self.pyzk_connections = {}
        self.fpmachine_connections = {}
        self.cleanup_temp_files()
        
    def connect_to_device(self, ip_address: str, port: int = 4370, timeout: int = 30, retries: int = 3) -> Optional[Any]:
        """Connect to a ZKTeco device with proper error handling and retries"""
        for attempt in range(retries):
            try:
                logging.info(f"Connecting to device at {ip_address} (attempt {attempt + 1}/{retries})...")
                zk = ZK(ip_address, port=port, timeout=timeout, ommit_ping=True)
                conn = zk.connect()
                logging.info(f"Successfully connected to device at {ip_address}")
                return conn
            except Exception as e:
                logging.error(f"Error connecting to device {ip_address} (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(2)  # Wait before retrying
        return None
    
    def cleanup_temp_files(self):
        """Clean up any temporary files created during sync operations"""
        try:
            # Clean up log files older than 7 days
            temp_patterns = [
                '*.tmp',
                'temp_*.log',
                'sync_*.temp',
                'face_sync_*.log',
                'complete_hybrid_sync.log',
                'final_face_sync_demo.log'
            ]
            
            current_time = time.time()
            seven_days = 7 * 24 * 60 * 60  # 7 days in seconds
            
            for pattern in temp_patterns:
                for file_path in glob.glob(pattern):
                    try:
                        file_age = current_time - os.path.getmtime(file_path)
                        if file_age > seven_days:
                            os.remove(file_path)
                            logging.info(f"Cleaned up old temp file: {file_path}")
                    except Exception as e:
                        logging.warning(f"Could not remove temp file {file_path}: {e}")
                        
        except Exception as e:
            logging.warning(f"Error during temp file cleanup: {e}")
    
    def get_valid_users_for_device(self, device_area_id: int) -> Dict[str, Dict]:
        """Get valid users for a specific device area from database"""
        valid_users = {}
        
        if not DATABASE_AVAILABLE:
            logging.warning("Database not available - cannot validate users")
            return valid_users
        
        try:
            # Get users that should be on this device:
            # 1. Status = 'Active' (not terminated)
            # 2. area_id matches device area OR area_id is None (global users)
            users = User.query.filter(
                User.status == 'Active',
                db.or_(User.area_id == device_area_id, User.area_id.is_(None))
            ).all()
            
            for user in users:
                valid_users[user.user_id] = {
                    'user_id': user.user_id,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'area_id': user.area_id,
                    'status': user.status
                }
            
            logging.info(f"Found {len(valid_users)} valid users for device area {device_area_id}")
            
        except Exception as e:
            logging.error(f"Error getting valid users from database: {e}")
        
        return valid_users
    
    def get_users_to_remove_from_device(self, device_conn, device_area_id: int) -> List[str]:
        """Get list of user IDs that should be removed from device"""
        users_to_remove = []
        
        if not DATABASE_AVAILABLE:
            return users_to_remove
        
        try:
            # Get all users currently on device
            device_users = device_conn.get_users() or []
            
            # Get valid users for this device area
            valid_users = self.get_valid_users_for_device(device_area_id)
            
            for device_user in device_users:
                user_id = device_user.user_id
                
                # Check if user should be removed
                should_remove = False
                
                # Check in database
                db_user = User.query.filter_by(user_id=user_id).first()
                
                if db_user:
                    # Remove if terminated
                    if db_user.status == 'Terminated':
                        should_remove = True
                        logging.info(f"User {user_id} marked for removal: status = Terminated")
                    
                    # Remove if area doesn't match (and user is not global)
                    elif db_user.area_id is not None and db_user.area_id != device_area_id:
                        should_remove = True
                        logging.info(f"User {user_id} marked for removal: area mismatch (user area: {db_user.area_id}, device area: {device_area_id})")
                
                else:
                    # User not found in database - remove from device
                    should_remove = True
                    logging.info(f"User {user_id} marked for removal: not found in database")
                
                if should_remove:
                    users_to_remove.append(user_id)
            
            logging.info(f"Found {len(users_to_remove)} users to remove from device")
            
        except Exception as e:
            logging.error(f"Error determining users to remove: {e}")
        
        return users_to_remove
    
    def sync_new_users_from_database_to_device(self, device_conn, device_area_id: int) -> Dict[str, int]:
        """Add new users from database to device that don't exist on device yet"""
        result = {'users_added': 0, 'errors': 0}
        
        if not DATABASE_AVAILABLE:
            logging.info("Database not available - cannot sync new users")
            return result
        
        try:
            # Get all users currently on device
            device_users = device_conn.get_users() or []
            device_user_ids = {user.user_id for user in device_users}
            
            # Get valid users for this device area from database
            valid_users = self.get_valid_users_for_device(device_area_id)
            
            # Find users that exist in database but not on device
            users_to_add = []
            for user_id, user_data in valid_users.items():
                if user_id not in device_user_ids:
                    users_to_add.append(user_data)
            
            if not users_to_add:
                logging.info(f"No new users to add to device (area {device_area_id})")
                return result
            
            logging.info(f"Adding {len(users_to_add)} new users from database to device")
            
            # Find next available UID on device
            existing_uids = {user.uid for user in device_users}
            next_uid = 1
            while next_uid in existing_uids:
                next_uid += 1
            
            for user_data in users_to_add:
                try:
                    # Create user object for device
                    user_name = f"{user_data['first_name']} {user_data['last_name']}".strip()
                    
                    # Add user to device
                    success = device_conn.set_user(
                        uid=next_uid,
                        name=user_name,
                        privilege=0,  # Normal user
                        password='',
                        group_id='',
                        user_id=user_data['user_id'],
                        card=0
                    )
                    
                    if success:
                        result['users_added'] += 1
                        logging.info(f"Added user {user_data['user_id']} ({user_name}) to device with UID {next_uid}")
                        next_uid += 1
                    else:
                        result['errors'] += 1
                        logging.warning(f"Failed to add user {user_data['user_id']} to device")
                        
                except Exception as e:
                    logging.error(f"Error adding user {user_data['user_id']}: {e}")
                    result['errors'] += 1
            
            logging.info(f"Added {result['users_added']} new users to device, {result['errors']} errors")
            
        except Exception as e:
            logging.error(f"Error in sync_new_users_from_database_to_device: {e}")
            result['errors'] += 1
        
        return result
    
    def remove_invalid_users_from_device(self, device_conn, device_area_id: int, progress_callback=None) -> Dict[str, int]:
        """Remove terminated and area-mismatched users from device"""
        result = {'users_removed': 0, 'templates_removed': 0, 'errors': 0}
        
        try:
            users_to_remove = self.get_users_to_remove_from_device(device_conn, device_area_id)
            
            if not users_to_remove:
                logging.info("No users need to be removed from device")
                return result
            
            logging.info(f"Removing {len(users_to_remove)} invalid users from device")
            if progress_callback:
                progress_callback(f"Removing {len(users_to_remove)} terminated users from device...")
            
            # Get all device users ONCE, not in the loop
            device_users = device_conn.get_users() or []
            user_uid_map = {user.user_id: user.uid for user in device_users}
            
            # Process in batches to provide progress updates
            batch_size = 10
            for i, user_id in enumerate(users_to_remove):
                if progress_callback and i % batch_size == 0:
                    progress_callback(f"Removing users... ({i+1}/{len(users_to_remove)})")
                
                # Add small delay every 5 users to prevent blocking
                if i % 5 == 0 and i > 0:
                    time.sleep(0.1)  # 100ms pause
                    
                try:
                    user_uid = user_uid_map.get(user_id)
                    
                    if user_uid is not None:
                        # Remove user (this also removes associated templates)
                        try:
                            device_conn.delete_user(uid=user_uid)
                            result['users_removed'] += 1
                            logging.info(f"Removed user {user_id} (UID: {user_uid}) from device")
                        except Exception as delete_error:
                            result['errors'] += 1
                            logging.warning(f"Failed to remove user {user_id} from device: {delete_error}")
                    else:
                        logging.warning(f"Could not find UID for user {user_id} on device")
                        result['errors'] += 1
                        
                except Exception as e:
                    logging.error(f"Error removing user {user_id}: {e}")
                    result['errors'] += 1
            
        except Exception as e:
            logging.error(f"Error in remove_invalid_users_from_device: {e}")
            result['errors'] += 1
        
        return result
    
    def get_device_data(self, conn, ip_address: str) -> Dict[str, Any]:
        """Get comprehensive device data including users, templates, and photos"""
        try:
            logging.info(f"Fetching data from device {ip_address}...")
            start_time = time.time()
            
            # Get all users
            users = conn.get_users()
            if users is None:
                users = []
            user_fetch_time = time.time()
            logging.info(f"Found {len(users)} users on device {ip_address} in {user_fetch_time - start_time:.2f} seconds")
            
            # Organize user data
            user_dict = {user.user_id: user for user in users}
            
            # Get all templates in bulk
            all_templates = conn.get_templates()
            if all_templates is None:
                all_templates = []
            template_fetch_time = time.time()
            logging.info(f"Found {len(all_templates)} fingerprint templates on device {ip_address} in {template_fetch_time - user_fetch_time:.2f} seconds")
            
            # Group templates by user_id
            user_templates = {}
            uid_to_user_id = {user.uid: user.user_id for user in users}
            
            for template in all_templates:
                user_id = uid_to_user_id.get(template.uid)
                if user_id:
                    if user_id not in user_templates:
                        user_templates[user_id] = []
                    user_templates[user_id].append(template)
            
            # Get face templates count (but don't fetch them with pyzk - use fpmachine instead)
            face_templates = {}
            face_count = 0
            
            try:
                # Check if device has face support using attributes
                if hasattr(conn, 'faces'):
                    face_count = conn.faces
                    logging.info(f"Device has {face_count} face templates according to faces attribute")
                
                # NOTE: We skip pyzk face template fetching since it doesn't have send_command
                # Face templates will be synced using fpmachine library instead
                if face_count > 0:
                    logging.info(f"Face templates detected on {ip_address} - will be synced using fpmachine")
                else:
                    logging.info(f"No face templates detected on {ip_address}")
                    
            except Exception as e:
                logging.warning(f"Error checking face templates: {e}")
            
            face_template_time = time.time()
            logging.info(f"Found {len(face_templates)} face templates on device {ip_address} in {face_template_time - template_fetch_time:.2f} seconds")
            
            # Skip user photos (use fpmachine instead)
            user_photos = {}
            
            # NOTE: We skip pyzk photo fetching since it doesn't have send_command
            # Photos will be synced using fpmachine library instead
            logging.info(f"Skipping pyzk photo fetch - will use fpmachine for photo sync")
            
            photo_fetch_time = time.time()
            logging.info(f"Photo check completed in {photo_fetch_time - face_template_time:.2f} seconds")
            
            total_time = time.time() - start_time
            logging.info(f"Completed data fetch from {ip_address} in {total_time:.2f} seconds")
            
            return {
                'users': user_dict,
                'fingerprint_templates': user_templates,
                'face_templates': face_templates,
                'user_photos': user_photos,
                'user_count': len(users),
                'template_count': len(all_templates) + len(face_templates)
            }
            
        except Exception as e:
            logging.error(f"Error fetching data from device {ip_address}: {e}")
            return {
                'users': {},
                'fingerprint_templates': {},
                'face_templates': {},
                'user_photos': {},
                'user_count': 0,
                'template_count': 0
            }
    
    def get_device_data_limited(self, conn, ip_address: str, users: List[Any]) -> Dict[str, Any]:
        """Get device data for a limited set of users (for faster testing)"""
        try:
            logging.info(f"Fetching limited data from {ip_address} for {len(users)} users...")
            start_time = time.time()
            
            # Organize user data
            user_dict = {user.user_id: user for user in users}
            
            # Get all templates in bulk and filter for our users
            all_templates = conn.get_templates()
            if all_templates is None:
                all_templates = []
            
            # Group templates by user_id for our limited users
            user_templates = {}
            uid_to_user_id = {user.uid: user.user_id for user in users}
            
            for template in all_templates:
                user_id = uid_to_user_id.get(template.uid)
                if user_id:
                    if user_id not in user_templates:
                        user_templates[user_id] = []
                    user_templates[user_id].append(template)
            
            template_fetch_time = time.time()
            logging.info(f"Found {len(user_templates)} users with fingerprint templates in {template_fetch_time - start_time:.2f} seconds")
            
            # Skip face templates for limited users (use fpmachine instead)
            face_templates = {}
            face_count = 0
            
            # NOTE: We skip pyzk face template fetching since it doesn't have send_command
            # Face templates will be synced using fpmachine library instead
            logging.info(f"Skipping pyzk face template fetch - will use fpmachine for face sync")
            
            face_template_time = time.time()
            logging.info(f"Face template check completed in {face_template_time - template_fetch_time:.2f} seconds")
            
            # Skip user photos for limited users (use fpmachine instead)
            user_photos = {}
            photo_count = 0
            
            # NOTE: We skip pyzk photo fetching since it doesn't have send_command
            # Photos will be synced using fpmachine library instead
            logging.info(f"Skipping pyzk photo fetch - will use fpmachine for photo sync")
            
            photo_fetch_time = time.time()
            logging.info(f"Photo check completed in {photo_fetch_time - face_template_time:.2f} seconds")
            
            total_time = time.time() - start_time
            logging.info(f"Completed limited data fetch from {ip_address} in {total_time:.2f} seconds")
            
            return {
                'users': user_dict,
                'fingerprint_templates': user_templates,
                'face_templates': face_templates,
                'user_photos': user_photos,
                'user_count': len(users),
                'template_count': len(user_templates) + face_count
            }
            
        except Exception as e:
            logging.error(f"Error fetching limited data from device {ip_address}: {e}")
            return {
                'users': {},
                'fingerprint_templates': {},
                'face_templates': {},
                'user_photos': {},
                'user_count': 0,
                'template_count': 0
            }
    
    def get_face_template(self, conn, user) -> Optional[Any]:
        """Attempt to get face template for a specific user using proper protocol"""
        try:
            # Method 1: Try standard get_face_template if available
            if hasattr(conn, 'get_face_template'):
                try:
                    result = conn.get_face_template(uid=user.uid)
                    if result and len(result) > 0:
                        return result
                except Exception as e:
                    logging.debug(f"Standard get_face_template failed for user {user.user_id}: {e}")
            
            # Method 2: Use raw command protocol with proper structure
            try:
                import struct
                command_data = struct.pack('<I', user.uid)
                result = conn.send_command(1503, command_data)  # CMD_GET_FACE_TEMPLATE
                if result and len(result) > 4:
                    template_size = struct.unpack('<I', result[:4])[0]
                    if template_size > 0 and len(result) >= 4 + template_size:
                        return result[4:4+template_size]
            except Exception as e:
                logging.debug(f"Raw face template command failed for user {user.user_id}: {e}")
            
            # Method 3: Try read_with_buffer with different commands
            for cmd in [1503, 1504, 1505]:
                try:
                    result = conn.read_with_buffer(cmd, user.uid)
                    if result and len(result) > 0:
                        return result
                except:
                    continue
                    
        except Exception as e:
            logging.debug(f"Error getting face template for user {user.user_id}: {e}")
            
        return None
    
    def connect_fpmachine(self, ip_address: str) -> Optional[Any]:
        """Connect using fpmachine library for face templates and photos"""
        try:
            from fpmachine.devices import ZMM220_TFT
            dev = ZMM220_TFT(ip_address, 4370, "latin-1")
            if dev.connect(0):
                self.fpmachine_connections[ip_address] = dev
                logging.info(f"fpmachine connected to {ip_address}")
                return dev
        except Exception as e:
            logging.error(f"fpmachine connection failed for {ip_address}: {e}")
        return None
    
    def get_users_with_face_data_fpmachine(self, ip_address: str) -> Dict[str, Dict[str, Any]]:
        """Get users with face templates and photos using fpmachine (WORKING METHOD)"""
        
        if ip_address not in self.fpmachine_connections:
            logging.error(f"No fpmachine connection for {ip_address}")
            return {}
        
        dev = self.fpmachine_connections[ip_address]
        users_with_face_data = {}
        
        try:
            users = dev.get_users()
            if not users:
                return {}
            
            logging.info(f"Checking {len(users)} users for face/photo data on {ip_address}")
            
            for i, user in enumerate(users):
                if i % 50 == 0:
                    logging.info(f"  Progress: {i}/{len(users)} users checked")
                
                user_id = getattr(user, 'person_id', getattr(user, 'id', str(i)))
                user_name = getattr(user, 'name', f'User_{i}')
                
                user_data = {
                    'user_object': user,
                    'user_id': user_id,
                    'user_name': user_name,
                    'face_template': None,
                    'photo': None,
                    'has_face_data': False
                }
                
                # Check for face template
                try:
                    face_data = dev.get_user_face(str(user_id))
                    if face_data and len(face_data) > 0:
                        user_data['face_template'] = face_data
                        user_data['has_face_data'] = True
                except Exception as e:
                    logging.debug(f"No face template for user {user_id}: {e}")
                
                # Check for photo
                try:
                    photo_data = dev.get_user_pic(str(user_id))
                    if photo_data and len(photo_data) > 0:
                        user_data['photo'] = photo_data
                        user_data['has_face_data'] = True
                except Exception as e:
                    logging.debug(f"No photo for user {user_id}: {e}")
                
                if user_data['has_face_data']:
                    users_with_face_data[user_id] = user_data
            
            logging.info(f"Found {len(users_with_face_data)} users with face/photo data on {ip_address}")
            
        except Exception as e:
            logging.error(f"Error getting face data from {ip_address}: {e}")
        
        return users_with_face_data
    
    def sync_face_and_photos_fpmachine(self, source_ip: str, target_ip: str) -> Dict[str, int]:
        """Sync face templates and photos using fpmachine (WORKING METHOD)"""
        
        if source_ip not in self.fpmachine_connections or target_ip not in self.fpmachine_connections:
            logging.error("Both devices must be connected via fpmachine for face sync")
            return {'face_templates_synced': 0, 'photos_synced': 0, 'errors': 0}
        
        source_dev = self.fpmachine_connections[source_ip]
        target_dev = self.fpmachine_connections[target_ip]
        
        # Get users with face data from source
        source_face_data = self.get_users_with_face_data_fpmachine(source_ip)
        
        if not source_face_data:
            logging.info(f"No face data found on source device {source_ip}")
            return {'face_templates_synced': 0, 'photos_synced': 0, 'errors': 0}
        
        logging.info(f"Found {len(source_face_data)} users with face/photo data on {source_ip}")
        
        # Check which users already have face data on target device
        users_to_sync = {}
        users_already_exist = 0
        
        for user_id, face_data in source_face_data.items():
            # Check if user already has face data on target
            existing_face = None
            existing_photo = None
            
            try:
                existing_face = target_dev.get_user_face(str(user_id))
            except:
                pass
            
            try:
                existing_photo = target_dev.get_user_pic(str(user_id))
            except:
                pass
            
            if existing_face or existing_photo:
                users_already_exist += 1
                logging.debug(f"User {user_id} already has face data on {target_ip}, skipping")
            else:
                users_to_sync[user_id] = face_data
        
        logging.info(f"Face sync analysis: {len(users_to_sync)} new users to sync, {users_already_exist} users already have face data")
        
        if not users_to_sync:
            logging.info(f"No new face data to sync - all users already have face data on {target_ip}")
            return {'face_templates_synced': 0, 'photos_synced': 0, 'errors': 0}
        
        logging.info(f"Syncing face data from {source_ip} to {target_ip} for {len(users_to_sync)} new users")
        
        results = {'face_templates_synced': 0, 'photos_synced': 0, 'errors': 0}
        
        for user_id, face_data in users_to_sync.items():
            try:
                # Sync face template
                if face_data['face_template']:
                    try:
                        success = target_dev.set_user_face(str(user_id), face_data['face_template'])
                        if success:
                            results['face_templates_synced'] += 1
                            logging.info(f"Synced face template for user {user_id} ({face_data['user_name']})")
                        else:
                            logging.warning(f"Failed to sync face template for user {user_id}")
                            results['errors'] += 1
                    except Exception as e:
                        logging.error(f"Error syncing face template for user {user_id}: {e}")
                        results['errors'] += 1
                
                # Sync photo
                if face_data['photo']:
                    try:
                        success = target_dev.set_user_pic(str(user_id), face_data['photo'])
                        if success:
                            results['photos_synced'] += 1
                            logging.info(f"Synced photo for user {user_id} ({face_data['user_name']})")
                        else:
                            logging.warning(f"Failed to sync photo for user {user_id}")
                            results['errors'] += 1
                    except Exception as e:
                        logging.error(f"Error syncing photo for user {user_id}: {e}")
                        results['errors'] += 1
                        
            except Exception as e:
                logging.error(f"Error syncing data for user {user_id}: {e}")
                results['errors'] += 1
        
        return results
    
    def get_user_photo(self, conn, user_uid: int) -> Optional[Any]:
        """Get user photo from device using proper protocol"""
        try:
            # Method 1: Try standard get_user_photo if available
            if hasattr(conn, 'get_user_photo'):
                try:
                    result = conn.get_user_photo(uid=user_uid)
                    if result and len(result) > 0:
                        return result
                except Exception as e:
                    logging.debug(f"Standard get_user_photo failed for UID {user_uid}: {e}")
            
            # Method 2: Use raw command protocol with proper structure
            try:
                import struct
                command_data = struct.pack('<I', user_uid)
                result = conn.send_command(1505, command_data)  # CMD_GET_USER_PHOTO
                if result and len(result) > 4:
                    photo_size = struct.unpack('<I', result[:4])[0]
                    if photo_size > 0 and len(result) >= 4 + photo_size:
                        return result[4:4+photo_size]
            except Exception as e:
                logging.debug(f"Raw photo command failed for UID {user_uid}: {e}")
            
            # Method 3: Try alternative methods for getting photos
            for cmd in [1505, 1506, 1507]:  # Common photo commands
                try:
                    result = conn.read_with_buffer(cmd, user_uid)
                    if result and len(result) > 0:
                        return result
                except:
                    continue
                    
        except Exception as e:
            logging.debug(f"Error getting photo for UID {user_uid}: {e}")
            
        return None
    
    def save_user_templates(self, conn, user_uid: int, templates: List[Any]) -> bool:
        """Save fingerprint templates for a user"""
        if not templates:
            return False
            
        try:
            # Save templates using the correct API
            result = conn.save_user_template(user=user_uid, fingers=templates)
            return result is not False
        except Exception as e:
            logging.error(f"Error saving templates for UID {user_uid}: {e}")
            return False
    
    def save_face_template(self, conn, user_uid: int, face_template: Any) -> bool:
        """Attempt to save face template using proper protocol"""
        try:
            # Method 1: Check if device has save_face_template method
            if hasattr(conn, 'save_face_template'):
                try:
                    result = conn.save_face_template(uid=user_uid, template=face_template)
                    if result:
                        return True
                except Exception as e:
                    logging.debug(f"Standard save_face_template failed for UID {user_uid}: {e}")
            
            # Method 2: Use raw command protocol with proper structure
            try:
                import struct
                if isinstance(face_template, bytes):
                    template_data = face_template
                else:
                    template_data = bytes(face_template)
                
                template_size = len(template_data)
                command_data = struct.pack('<II', user_uid, template_size) + template_data
                result = conn.send_command(1504, command_data)  # CMD_SET_FACE_TEMPLATE
                return result is not None
            except Exception as e:
                logging.debug(f"Raw save face template command failed for UID {user_uid}: {e}")
            
            # Method 3: Try alternative raw command format
            try:
                # Some devices might expect different format
                command_string = f"{user_uid}:{face_template}".encode()
                result = conn.send_command(1504, command_string)
                return result is not None
            except Exception as e:
                logging.debug(f"Alternative face template save failed for UID {user_uid}: {e}")
            
            logging.warning(f"Face template saving not supported for UID {user_uid}")
            return False
            
        except Exception as e:
            logging.error(f"Error saving face template for UID {user_uid}: {e}")
            return False
    
    def save_user_photo(self, conn, user_uid: int, photo_data: Any) -> bool:
        """Save user photo to device using proper protocol"""
        try:
            # Method 1: Check if device supports standard photo operations
            if hasattr(conn, 'set_user_photo'):
                try:
                    result = conn.set_user_photo(uid=user_uid, photo=photo_data)
                    if result:
                        return True
                except Exception as e:
                    logging.debug(f"Standard set_user_photo failed for UID {user_uid}: {e}")
            
            # Method 2: Use raw command protocol with proper structure
            try:
                import struct
                if isinstance(photo_data, bytes):
                    photo_bytes = photo_data
                else:
                    photo_bytes = bytes(photo_data)
                
                photo_size = len(photo_bytes)
                command_data = struct.pack('<II', user_uid, photo_size) + photo_bytes
                result = conn.send_command(1506, command_data)  # CMD_SET_USER_PHOTO
                return result is not None
            except Exception as e:
                logging.debug(f"Raw save photo command failed for UID {user_uid}: {e}")
            
            # Method 3: Alternative method for devices that use different format
            try:
                # Some devices use different commands for photos
                command_string = f"{user_uid}:{photo_data}".encode()
                result = conn.send_command(1506, command_string)
                return result is not None
            except Exception as e:
                logging.debug(f"Alternative photo save failed for UID {user_uid}: {e}")
            
            logging.warning(f"Photo saving not supported for UID {user_uid}")
            return False
            
        except Exception as e:
            logging.error(f"Error saving photo for UID {user_uid}: {e}")
            return False
    
    def get_device_data_with_face_support(self, conn, ip_address: str, face_supported: bool) -> Dict[str, Any]:
        """Get device data with optional face template fetching based on support"""
        try:
            logging.info(f"Fetching data from device {ip_address}...")
            start_time = time.time()
            
            # Get all users
            users = conn.get_users()
            if users is None:
                users = []
            user_fetch_time = time.time()
            logging.info(f"Found {len(users)} users on device {ip_address} in {user_fetch_time - start_time:.2f} seconds")
            
            # Organize user data
            user_dict = {user.user_id: user for user in users}
            
            # Get all templates in bulk
            all_templates = conn.get_templates()
            if all_templates is None:
                all_templates = []
            template_fetch_time = time.time()
            logging.info(f"Found {len(all_templates)} fingerprint templates on device {ip_address} in {template_fetch_time - user_fetch_time:.2f} seconds")
            
            # Group templates by user_id
            user_templates = {}
            uid_to_user_id = {user.uid: user.user_id for user in users}
            
            for template in all_templates:
                user_id = uid_to_user_id.get(template.uid)
                if user_id:
                    if user_id not in user_templates:
                        user_templates[user_id] = []
                    user_templates[user_id].append(template)
            
            # Get face templates only if supported
            face_templates = {}
            face_count = 0
            
            if face_supported:
                try:
                    # Check if device has face support using attributes
                    if hasattr(conn, 'faces'):
                        face_count = conn.faces
                        logging.info(f"Device has {face_count} face templates according to faces attribute")
                    
                    # Note: Face templates will be synced using fpmachine, not pyzk
                    # pyzk doesn't have send_command method for face templates
                    logging.info(f"Face templates detected on {ip_address} - will be synced using fpmachine")
                    
                except Exception as e:
                    logging.warning(f"Error checking face templates: {e}")
            else:
                logging.info(f"Skipping face template fetch for {ip_address} (not supported)")
            
            face_template_time = time.time()
            if face_supported:
                logging.info(f"Found {len(face_templates)} face templates on device {ip_address} in {face_template_time - template_fetch_time:.2f} seconds")
            
            # Get user photos (check if device supports photos first)
            user_photos = {}
            photo_errors = 0
            
            # Test photo support with first user
            photo_supported = False
            if users:
                try:
                    test_photo = self.get_user_photo(conn, users[0].uid)
                    photo_supported = True
                    if test_photo:
                        user_photos[users[0].user_id] = test_photo
                except Exception as e:
                    if "'ZK' object has no attribute 'send_command'" in str(e):
                        logging.info(f"Device {ip_address} does not support photo fetching (no send_command)")
                        photo_supported = False
                    else:
                        logging.debug(f"Photo test failed for {ip_address}: {e}")
                        photo_supported = False  # Don't try other users if test fails
            
            if photo_supported and len(users) > 1:
                # Fetch photos for remaining users
                for user in users[1:]:  # Skip first user (already tested)
                    try:
                        photo = self.get_user_photo(conn, user.uid)
                        if photo:
                            user_photos[user.user_id] = photo
                    except Exception as e:
                        photo_errors += 1
                        if photo_errors <= 3:  # Only log first few errors
                            logging.debug(f"Error getting photo for user {user.user_id}: {e}")
            
            photo_fetch_time = time.time()
            if photo_supported:
                logging.info(f"Found {len(user_photos)} user photos in {photo_fetch_time - face_template_time:.2f} seconds")
            else:
                logging.info(f"Skipping photo fetch for {ip_address} (not supported)")
            
            total_time = time.time() - start_time
            logging.info(f"Completed data fetch from {ip_address} in {total_time:.2f} seconds")
            
            return {
                'users': user_dict,
                'fingerprint_templates': user_templates,
                'face_templates': face_templates,
                'user_photos': user_photos,
                'user_count': len(users),
                'template_count': len(all_templates) + len(face_templates)
            }
            
        except Exception as e:
            logging.error(f"Error fetching data from device {ip_address}: {e}")
            return {
                'users': {},
                'fingerprint_templates': {},
                'face_templates': {},
                'user_photos': {},
                'user_count': 0,
                'template_count': 0
            }
    
    def check_device_face_support(self, conn, ip_address: str, users_fetched: bool = False) -> Dict[str, Any]:
        """Check if device supports face templates and photos
        
        IMPORTANT: users_fetched should be True if users have already been fetched,
        as this populates the faces attribute correctly.
        """
        support_info = {
            'ip_address': ip_address,
            'face_templates_supported': False,
            'photos_supported': True,  # Most devices support photos
            'face_function_enabled': False,
            'face_version': 0,
            'device_info': {},
            'detection_method': 'unknown',
            'face_count': 0
        }
        
        try:
            # Get device info (if available)
            try:
                device_info = conn.get_device_info()
                support_info['device_info'] = device_info
            except AttributeError:
                logging.debug(f"Device {ip_address} does not have get_device_info method")
                support_info['device_info'] = {}
            
            # Method 1: Check faces attribute (MOST RELIABLE after users are fetched)
            if hasattr(conn, 'faces'):
                face_count = conn.faces
                support_info['face_count'] = face_count
                logging.info(f"Device {ip_address} faces attribute: {face_count} (users_fetched: {users_fetched})")
                
                if face_count > 0:
                    support_info['face_templates_supported'] = True
                    support_info['detection_method'] = 'faces_attribute_positive'
                    logging.info(f"✓ Device {ip_address} SUPPORTS face templates ({face_count} faces detected)")
                elif users_fetched and face_count == 0:
                    # Users were fetched but still 0 faces - device doesn't have face templates
                    support_info['face_templates_supported'] = False
                    support_info['detection_method'] = 'faces_attribute_zero_after_fetch'
                    logging.info(f"✗ Device {ip_address} does NOT support face templates (0 faces after user fetch)")
                else:
                    # Users not fetched yet, faces attribute might not be populated
                    logging.info(f"⚠️ Device {ip_address} faces attribute is {face_count}, but users not fetched yet")
            else:
                logging.info(f"Device {ip_address} does not have 'faces' attribute")
            
            # Method 2: Check face function (if not determined yet)
            if not support_info['face_templates_supported'] and support_info['detection_method'] == 'unknown':
                try:
                    if hasattr(conn, 'get_face_fun_on'):
                        face_fun = conn.get_face_fun_on()
                        support_info['face_function_enabled'] = bool(face_fun)
                        if face_fun:
                            support_info['face_templates_supported'] = True
                            support_info['detection_method'] = 'face_function'
                            logging.info(f"✓ Device {ip_address} supports face templates (face function enabled)")
                        else:
                            logging.info(f"Device {ip_address} face function disabled")
                except Exception as e:
                    logging.debug(f"Could not check face function for {ip_address}: {e}")
            
            # Method 3: Check face version (if not determined yet)
            if not support_info['face_templates_supported'] and support_info['detection_method'] == 'unknown':
                try:
                    if hasattr(conn, 'get_face_version'):
                        face_version = conn.get_face_version()
                        support_info['face_version'] = face_version
                        if face_version and face_version > 0:
                            support_info['face_templates_supported'] = True
                            support_info['detection_method'] = 'face_version'
                            logging.info(f"✓ Device {ip_address} supports face templates (face version: {face_version})")
                        else:
                            logging.info(f"Device {ip_address} face version: {face_version}")
                except Exception as e:
                    logging.debug(f"Could not check face version for {ip_address}: {e}")
            
            # Final determination
            if support_info['face_templates_supported']:
                logging.info(f"🎯 FINAL: Device {ip_address} SUPPORTS face templates (method: {support_info['detection_method']}, count: {support_info['face_count']})")
            else:
                logging.info(f"🎯 FINAL: Device {ip_address} does NOT support face templates (method: {support_info['detection_method']})")
            
        except Exception as e:
            logging.error(f"Error checking face support for {ip_address}: {e}")
        
        return support_info
    
    def sync_specific_devices(self, device_ips: List[str], progress_callback=None) -> Dict[str, Any]:
        """Sync specific devices by IP addresses"""
        sync_key = f"specific_sync_{'_'.join(device_ips)}"
        
        if sync_key in self.sync_in_progress:
            return {
                'success': False,
                'message': 'Sync already in progress for these devices',
                'synced_devices': 0,
                'total_users_synced': 0,
                'total_templates_synced': 0
            }
        
        self.sync_in_progress.add(sync_key)
        device_connections = {}
        face_support_status = {}
        
        try:
            logging.info(f"Starting specific device sync for IPs: {device_ips}")
            
            # Step 1: Connect to all specified devices
            device_data = {}
            
            for i, ip_address in enumerate(device_ips):
                if progress_callback:
                    progress_callback(f"Connecting to device {ip_address} ({i+1}/{len(device_ips)})...")
                    
                conn = self.connect_to_device(ip_address)
                if conn:
                    device_connections[ip_address] = conn
                    
                    if progress_callback:
                        progress_callback(f"Getting device data from {ip_address}...")
                    
                    # Get device data first (this will fetch users and populate faces attribute)
                    device_data[ip_address] = self.get_device_data(conn, ip_address)
                    
                    # Check face support AFTER fetching users (for accurate detection)
                    face_support = self.check_device_face_support(conn, ip_address, users_fetched=True)
                    face_support_status[ip_address] = face_support
                    
                    logging.info(f"Device {ip_address}: Face support = {face_support['face_templates_supported']} ({face_support['face_count']} faces)")
                else:
                    logging.error(f"Could not connect to device {ip_address}")
                    if progress_callback:
                        progress_callback(f"Failed to connect to device {ip_address}")
            
            if not device_data:
                return {
                    'success': False,
                    'message': 'No devices could be connected',
                    'synced_devices': 0,
                    'total_users_synced': 0,
                    'total_templates_synced': 0,
                    'face_support_status': face_support_status
                }
            
            # Step 2: Determine primary device (most users + templates)
            primary_ip = max(device_data.keys(), 
                           key=lambda ip: device_data[ip]['user_count'] + device_data[ip]['template_count'])
            
            primary_data = device_data[primary_ip]
            logging.info(f"Primary device: {primary_ip} with {primary_data['user_count']} users "
                        f"and {primary_data['template_count']} templates")
            
            # Step 3: Clean up invalid users and add new users from database
            total_users_removed = 0
            total_users_added = 0
            for target_ip, target_conn in device_connections.items():
                try:
                    # Use area_id = 1 as default for specific device sync
                    cleanup_result = self.remove_invalid_users_from_device(target_conn, 1, progress_callback)
                    total_users_removed += cleanup_result['users_removed']
                    logging.info(f"Removed {cleanup_result['users_removed']} invalid users from {target_ip}")
                    
                    # Add new users from database
                    add_result = self.sync_new_users_from_database_to_device(target_conn, 1)
                    total_users_added += add_result['users_added']
                    logging.info(f"Added {add_result['users_added']} new users to {target_ip}")
                    
                except Exception as e:
                    logging.error(f"Error managing users on {target_ip}: {e}")
            
            # Step 4: Sync current date/time to all devices
            logging.info("🕐 Syncing current date/time to all devices...")
            if progress_callback:
                progress_callback("Syncing time to all devices...")
            for target_ip, target_conn in device_connections.items():
                try:
                    current_time = datetime.now()
                    target_conn.set_time(current_time)
                    logging.info(f"✅ Synced time {current_time.strftime('%Y-%m-%d %H:%M:%S')} to device {target_ip}")
                except Exception as e:
                    logging.warning(f"⚠️ Failed to sync time to device {target_ip}: {e}")
            
            # Step 5: Sync from primary to all other devices
            if progress_callback:
                progress_callback("Starting user and template sync between devices...")
            total_users_synced = 0
            total_templates_synced = 0
            total_face_synced = 0
            total_photos_synced = 0
            synced_devices = 0
            
            primary_conn = device_connections[primary_ip]
            
            # Connect fpmachine for face/photo sync (only for supported devices)
            for ip in device_connections.keys():
                if face_support_status[ip]['face_templates_supported']:
                    self.connect_fpmachine(ip)
                    logging.info(f"Connected fpmachine for {ip} (face support detected)")
                else:
                    logging.info(f"Skipping fpmachine connection for {ip} (no face support)")
            
            for i, (target_ip, target_data) in enumerate(device_data.items()):
                if target_ip == primary_ip:
                    continue
                
                if progress_callback:
                    progress_callback(f"Syncing users to device {target_ip}...")
                
                try:
                    # Sync users and fingerprints (pyzk)
                    result = self.sync_between_devices(
                        primary_conn, device_connections[target_ip],
                        primary_data, target_data,
                        primary_ip, target_ip
                    )
                    
                    # Small delay to prevent blocking
                    time.sleep(0.2)
                    
                    total_users_synced += result['users_synced']
                    total_templates_synced += result['templates_synced']
                    
                    # Sync face templates and photos (fpmachine) - only if supported
                    if (face_support_status[primary_ip]['face_templates_supported'] and 
                        face_support_status[target_ip]['face_templates_supported'] and
                        primary_ip in self.fpmachine_connections and 
                        target_ip in self.fpmachine_connections):
                        
                        logging.info(f"Syncing face templates between {primary_ip} and {target_ip}")
                        face_result = self.sync_face_and_photos_fpmachine(primary_ip, target_ip)
                        total_face_synced += face_result['face_templates_synced']
                        total_photos_synced += face_result['photos_synced']
                    else:
                        logging.info(f"Skipping face sync between {primary_ip} and {target_ip} (not supported)")
                    
                    synced_devices += 1
                    
                    logging.info(f"Synced {result['users_synced']} users and "
                               f"{result['templates_synced']} templates to {target_ip}")
                    
                except Exception as e:
                    logging.error(f"Error syncing to device {target_ip}: {e}")
                    continue
            
            # Set sync completion timestamp
            sync_completion_time = time.strftime('%Y-%m-%d %H:%M:%S')
            logging.info(f"🎯 SYNC COMPLETED at {sync_completion_time}")
            
            return {
                'success': True,
                'synced_devices': synced_devices,
                'total_users_synced': total_users_synced,
                'total_templates_synced': total_templates_synced,
                'total_face_templates_synced': total_face_synced,
                'total_photos_synced': total_photos_synced,
                'total_users_removed': total_users_removed,
                'total_users_added': total_users_added,
                'primary_device': primary_ip,
                'face_support_status': face_support_status,
                'sync_completion_time': sync_completion_time
            }
            
        except Exception as e:
            logging.error(f"Error in specific device sync: {e}")
            return {
                'success': False,
                'error': str(e),
                'synced_devices': 0,
                'total_users_synced': 0,
                'total_templates_synced': 0,
                'total_face_templates_synced': 0,
                'total_photos_synced': 0,
                'total_users_removed': 0,
                'face_support_status': face_support_status
            }
            
        finally:
            # Disconnect all devices
            for ip, conn in device_connections.items():
                try:
                    conn.disconnect()
                    logging.info(f"Disconnected from device {ip}")
                except Exception as e:
                    logging.warning(f"Error disconnecting from {ip}: {e}")
            
            # Disconnect fpmachine connections
            for ip, dev in self.fpmachine_connections.items():
                try:
                    dev.disconnect()
                    logging.info(f"Disconnected fpmachine from {ip}")
                except Exception as e:
                    logging.warning(f"Error disconnecting fpmachine from {ip}: {e}")
            
            # Clear connection caches
            self.pyzk_connections.clear()
            self.fpmachine_connections.clear()
            
            # Clean up temp files after sync
            self.cleanup_temp_files()
            
            # Remove from sync queue
            self.sync_in_progress.discard(sync_key)
    
    def sync_devices_in_area(self, area_id: int) -> Dict[str, Any]:
        """
        Comprehensive sync of all devices in an area with performance improvements
        """
        sync_key = f"area_sync_{area_id}"
        
        if sync_key in self.sync_in_progress:
            return {
                'success': False,
                'message': 'Sync already in progress for this area',
                'synced_devices': 0,
                'total_users_synced': 0,
                'total_templates_synced': 0
            }
        
        self.sync_in_progress.add(sync_key)
        device_connections = {}
        
        try:
            # Get all online devices in the area using Flask-SQLAlchemy
            try:
                from app import app, db
                from models import Device
                
                with app.app_context():
                    devices = db.session.query(Device.device_id, Device.ip_address).filter(
                        Device.area_id == area_id,
                        Device.online_status == True
                    ).all()
                    
            except Exception as e:
                logging.error(f"Error accessing database: {e}")
                return {
                    'success': False,
                    'message': f'Database error: {e}',
                    'synced_devices': 0,
                    'total_users_synced': 0,
                    'total_templates_synced': 0
                }
            
            if len(devices) < 2:
                return {
                    'success': True,
                    'message': 'Less than 2 devices in area - no sync needed',
                    'synced_devices': 0,
                    'total_users_synced': 0,
                    'total_templates_synced': 0
                }
            
            logging.info(f"Starting comprehensive sync for {len(devices)} devices in area {area_id}")
            
            # Step 1: Connect to all devices and collect data
            device_data = {}
            face_support_status = {}
            
            for device_id, ip_address in devices:
                conn = self.connect_to_device(ip_address)
                if conn:
                    device_connections[ip_address] = conn
                    
                    # Get device data first (this will fetch users and populate faces attribute)
                    device_data[ip_address] = self.get_device_data(conn, ip_address)
                    device_data[ip_address]['device_id'] = device_id
                    
                    # Check face support AFTER fetching users (for accurate detection)
                    face_support = self.check_device_face_support(conn, ip_address, users_fetched=True)
                    face_support_status[ip_address] = face_support
                    
                    logging.info(f"Device {ip_address}: Face support = {face_support['face_templates_supported']} ({face_support['face_count']} faces)")
            
            if not device_data:
                return {
                    'success': False,
                    'message': 'No devices could be connected',
                    'synced_devices': 0,
                    'total_users_synced': 0,
                    'total_templates_synced': 0
                }
            
            # Step 2: Determine primary device (most users + templates)
            primary_ip = max(device_data.keys(), 
                           key=lambda ip: device_data[ip]['user_count'] + device_data[ip]['template_count'])
            
            primary_data = device_data[primary_ip]
            logging.info(f"Primary device: {primary_ip} with {primary_data['user_count']} users "
                        f"and {primary_data['template_count']} templates")
            
            # Step 3: Clean up invalid users and add new users from database
            total_users_removed = 0
            total_users_added = 0
            for target_ip, target_conn in device_connections.items():
                try:
                    cleanup_result = self.remove_invalid_users_from_device(target_conn, area_id, None)
                    total_users_removed += cleanup_result['users_removed']
                    logging.info(f"Removed {cleanup_result['users_removed']} invalid users from {target_ip}")
                    
                    # Add new users from database
                    add_result = self.sync_new_users_from_database_to_device(target_conn, area_id)
                    total_users_added += add_result['users_added']
                    logging.info(f"Added {add_result['users_added']} new users to {target_ip}")
                    
                except Exception as e:
                    logging.error(f"Error managing users on {target_ip}: {e}")
            
            # Step 4: Sync current date/time to all devices
            logging.info("🕐 Syncing current date/time to all devices...")
            for target_ip, target_conn in device_connections.items():
                try:
                    current_time = datetime.now()
                    target_conn.set_time(current_time)
                    logging.info(f"✅ Synced time {current_time.strftime('%Y-%m-%d %H:%M:%S')} to device {target_ip}")
                except Exception as e:
                    logging.warning(f"⚠️ Failed to sync time to device {target_ip}: {e}")
            
            # Step 5: Comprehensive sync from primary to all other devices
            total_users_synced = 0
            total_templates_synced = 0
            total_face_synced = 0
            total_photos_synced = 0
            synced_devices = 0
            
            primary_conn = device_connections[primary_ip]
            
            # Connect fpmachine for face/photo sync (only for supported devices)
            for ip in device_connections.keys():
                if face_support_status[ip]['face_templates_supported']:
                    self.connect_fpmachine(ip)
                    logging.info(f"Connected fpmachine for {ip} (face support detected)")
                else:
                    logging.info(f"Skipping fpmachine connection for {ip} (no face support)")
            
            for target_ip, target_data in device_data.items():
                if target_ip == primary_ip:
                    continue
                
                try:
                    # Sync users and fingerprints (pyzk)
                    result = self.sync_between_devices(
                        primary_conn, device_connections[target_ip],
                        primary_data, target_data,
                        primary_ip, target_ip
                    )
                    
                    total_users_synced += result['users_synced']
                    total_templates_synced += result['templates_synced']
                    
                    # Sync face templates and photos (fpmachine) - only if supported
                    if (face_support_status[primary_ip]['face_templates_supported'] and 
                        face_support_status[target_ip]['face_templates_supported'] and
                        primary_ip in self.fpmachine_connections and 
                        target_ip in self.fpmachine_connections):
                        
                        logging.info(f"Syncing face templates between {primary_ip} and {target_ip}")
                        face_result = self.sync_face_and_photos_fpmachine(primary_ip, target_ip)
                        total_face_synced += face_result['face_templates_synced']
                        total_photos_synced += face_result['photos_synced']
                    else:
                        logging.info(f"Skipping face sync between {primary_ip} and {target_ip} (not supported)")
                    
                    synced_devices += 1
                    
                    logging.info(f"Synced {result['users_synced']} users and "
                               f"{result['templates_synced']} templates to {target_ip}")
                    
                except Exception as e:
                    logging.error(f"Error syncing to device {target_ip}: {e}")
                    continue
            
            # Set sync completion timestamp
            sync_completion_time = time.strftime('%Y-%m-%d %H:%M:%S')
            logging.info(f"🎯 SYNC COMPLETED at {sync_completion_time}")
            
            return {
                'success': True,
                'synced_devices': synced_devices,
                'total_users_synced': total_users_synced,
                'total_templates_synced': total_templates_synced,
                'total_face_templates_synced': total_face_synced,
                'total_photos_synced': total_photos_synced,
                'total_users_removed': total_users_removed,
                'total_users_added': total_users_added,
                'primary_device': primary_ip,
                'face_support_status': face_support_status,
                'sync_completion_time': sync_completion_time
            }
            
        except Exception as e:
            logging.error(f"Error in comprehensive area sync: {e}")
            return {
                'success': False,
                'error': str(e),
                'synced_devices': 0,
                'total_users_synced': 0,
                'total_templates_synced': 0,
                'total_face_templates_synced': 0,
                'total_photos_synced': 0,
                'total_users_removed': 0,
                'face_support_status': face_support_status if 'face_support_status' in locals() else {}
            }
            
        finally:
            # Disconnect all devices
            for ip, conn in device_connections.items():
                try:
                    conn.disconnect()
                    logging.info(f"Disconnected from device {ip}")
                except Exception as e:
                    logging.warning(f"Error disconnecting from {ip}: {e}")
            
            # Disconnect fpmachine connections
            for ip, dev in self.fpmachine_connections.items():
                try:
                    dev.disconnect()
                    logging.info(f"Disconnected fpmachine from {ip}")
                except Exception as e:
                    logging.warning(f"Error disconnecting fpmachine from {ip}: {e}")
            
            # Clear connection caches
            self.pyzk_connections.clear()
            self.fpmachine_connections.clear()
            
            # Clean up temp files after sync
            self.cleanup_temp_files()
            
            # Remove from sync queue
            self.sync_in_progress.discard(sync_key)
    
    def sync_between_devices(self, source_conn, target_conn, source_data, target_data, 
                           source_ip: str, target_ip: str) -> Dict[str, int]:
        """Sync users, templates, and photos between two specific devices"""
        
        users_synced = 0
        templates_synced = 0
        
        source_users = source_data['users']
        target_users = target_data['users']
        source_fingerprints = source_data['fingerprint_templates']
        source_faces = source_data['face_templates']
        source_photos = source_data['user_photos']
        
        # Find users missing on target device
        users_to_add = [user for user_id, user in source_users.items() 
                       if user_id not in target_users]
        
        if users_to_add:
            logging.info(f"Adding {len(users_to_add)} users from {source_ip} to {target_ip}")
            
            # Get existing UIDs on target device to avoid conflicts
            existing_uids = {user.uid for user in target_users.values()}
            max_uid = max(existing_uids) if existing_uids else 0
            
            for user in users_to_add:
                try:
                    # Try to preserve the original UID if possible
                    if user.uid not in existing_uids:
                        new_uid = user.uid
                    else:
                        # Find the next available UID
                        new_uid = max_uid + 1
                        max_uid += 1
                    
                    # Add user to target device
                    target_conn.set_user(
                        uid=new_uid,
                        name=user.name,
                        privilege=user.privilege,
                        password=user.password,
                        user_id=user.user_id,
                        group_id=getattr(user, 'group_id', ''),
                        card=getattr(user, 'card', 0)
                    )
                    users_synced += 1
                    
                    # Add user photo if available
                    if user.user_id in source_photos:
                        try:
                            if self.save_user_photo(target_conn, new_uid, source_photos[user.user_id]):
                                logging.info(f"Synced photo for user {user.user_id}")
                        except Exception as e:
                            logging.warning(f"Failed to sync photo for user {user.user_id}: {e}")
                    
                    # Add fingerprint templates if available
                    if user.user_id in source_fingerprints:
                        try:
                            finger_templates = source_fingerprints[user.user_id]
                            if self.save_user_templates(target_conn, new_uid, finger_templates):
                                templates_synced += len(finger_templates)
                                logging.info(f"Synced {len(finger_templates)} fingerprint templates for user {user.user_id}")
                        except Exception as e:
                            logging.warning(f"Failed to sync fingerprint for user {user.user_id}: {e}")
                    
                    # Add face templates if available
                    if user.user_id in source_faces:
                        try:
                            if self.save_face_template(target_conn, new_uid, source_faces[user.user_id]):
                                templates_synced += 1
                                logging.info(f"Synced face template for user {user.user_id}")
                        except Exception as e:
                            logging.warning(f"Failed to sync face template for user {user.user_id}: {e}")
                    
                    logging.info(f"Added user {user.user_id} to {target_ip} with UID {new_uid}")
                    
                except Exception as e:
                    logging.error(f"Error adding user {user.user_id} to {target_ip}: {e}")
        
        # Add missing templates and photos for existing users
        for user_id, user in source_users.items():
            if user_id in target_users:
                target_user = target_users[user_id]
                
                # Add missing photos
                if (user_id in source_photos and 
                    user_id not in target_data['user_photos']):
                    try:
                        if self.save_user_photo(target_conn, target_user.uid, source_photos[user_id]):
                            logging.info(f"Added photo for existing user {user_id}")
                    except Exception as e:
                        logging.warning(f"Failed to add photo for user {user_id}: {e}")
                
                # Add missing fingerprint templates
                if (user_id in source_fingerprints and 
                    (user_id not in target_data['fingerprint_templates'] or 
                     not target_data['fingerprint_templates'].get(user_id))):
                    try:
                        finger_templates = source_fingerprints[user_id]
                        if self.save_user_templates(target_conn, target_user.uid, finger_templates):
                            templates_synced += len(finger_templates)
                            logging.info(f"Added {len(finger_templates)} fingerprint templates for existing user {user_id}")
                    except Exception as e:
                        logging.warning(f"Failed to add fingerprint templates for user {user_id}: {e}")
                
                # Add missing face templates
                if (user_id in source_faces and 
                    user_id not in target_data['face_templates']):
                    try:
                        if self.save_face_template(target_conn, target_user.uid, source_faces[user_id]):
                            templates_synced += 1
                            logging.info(f"Added face template for existing user {user_id}")
                    except Exception as e:
                        logging.warning(f"Failed to add face template for user {user_id}: {e}")
        
        return {
            'users_synced': users_synced,
            'templates_synced': templates_synced
        }


def sync_devices_in_area(area_id: int) -> Dict[str, Any]:
    """Main function to sync devices in an area"""
    sync_manager = EnhancedDeviceSync()
    return sync_manager.sync_devices_in_area(area_id)


def update_devices(selected_ips: List[str]) -> str:
    """
    Enhanced version of your reference update_devices function
    Now handles both fingerprint and face templates with proper API calls
    """
    sync_manager = EnhancedDeviceSync()
    devices = {}
    
    # Connect to all devices
    for device_ip in selected_ips:
        conn = sync_manager.connect_to_device(device_ip)
        if conn:
            devices[device_ip] = conn
    
    if not devices:
        return "No devices could be connected"
    
    # Fetch all data from each device
    device_data = {}
    for device_ip, device_conn in devices.items():
        device_data[device_ip] = sync_manager.get_device_data(device_conn, device_ip)
        logging.info(f"Device {device_ip} has {device_data[device_ip]['user_count']} users "
                    f"and {device_data[device_ip]['template_count']} templates")
    
    # Find primary device (most users + templates)
    primary_ip = max(device_data.keys(), 
                   key=lambda ip: device_data[ip]['user_count'] + device_data[ip]['template_count'])
    
    logging.info(f"Using {primary_ip} as primary device")
    
    # Sync from primary to all other devices
    total_synced = 0
    for target_ip in devices.keys():
        if target_ip != primary_ip:
            try:
                result = sync_manager.sync_between_devices(
                    devices[primary_ip], devices[target_ip],
                    device_data[primary_ip], device_data[target_ip],
                    primary_ip, target_ip
                )
                total_synced += result['users_synced'] + result['templates_synced']
                logging.info(f"Synced {result['users_synced']} users and "
                           f"{result['templates_synced']} templates to {target_ip}")
            except Exception as e:
                logging.error(f"Error syncing to {target_ip}: {e}")
    
    # Disconnect from all devices
    for device_ip, device_conn in devices.items():
        try:
            device_conn.disconnect()
            logging.info(f"Disconnected from device {device_ip}")
        except Exception as e:
            logging.error(f"Error disconnecting from device {device_ip}: {e}")
    
    return f"Devices synchronized successfully. Total items synced: {total_synced}"