#!/usr/bin/env python3
"""
Enhanced Face Template and Photo Sync for ZKTeco Devices
Research-based implementation with proper face template handling
"""

import logging
import time
import struct
from typing import Dict, List, Optional, Any
from zk import ZK

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('face_sync.log'),
        logging.StreamHandler()
    ]
)

class EnhancedFaceSync:
    """Enhanced face template and photo sync with proper ZKTeco protocol handling"""
    
    # ZKTeco command constants for face templates and photos
    CMD_GET_FACE_TEMPLATE = 1503  # Get face template data
    CMD_SET_FACE_TEMPLATE = 1504  # Set face template data
    CMD_GET_USER_PHOTO = 1505     # Get user photo
    CMD_SET_USER_PHOTO = 1506     # Set user photo
    CMD_FACE_TEMPLATE_COUNT = 1507 # Get face template count
    
    def __init__(self):
        self.face_template_cache = {}
        self.photo_cache = {}
    
    def connect_to_device(self, ip_address: str, port: int = 4370, timeout: int = 15) -> Optional[Any]:
        """Connect to device with optimized settings"""
        try:
            logging.info(f"Connecting to {ip_address}...")
            zk = ZK(ip_address, port=port, timeout=timeout, ommit_ping=True)
            conn = zk.connect()
            logging.info(f"Connected to {ip_address}")
            return conn
        except Exception as e:
            logging.error(f"Failed to connect to {ip_address}: {e}")
            return None
    
    def get_face_template_raw(self, conn, uid: int) -> Optional[bytes]:
        """Get face template using raw command protocol"""
        try:
            # Method 1: Try the standard get_face_template if available
            if hasattr(conn, 'get_face_template'):
                try:
                    result = conn.get_face_template(uid=uid)
                    if result:
                        return result
                except Exception as e:
                    logging.debug(f"Standard get_face_template failed for UID {uid}: {e}")
            
            # Method 2: Use raw command protocol
            try:
                # Send command to get face template
                command_data = struct.pack('<I', uid)
                result = conn.send_command(self.CMD_GET_FACE_TEMPLATE, command_data)
                if result and len(result) > 4:
                    # Parse the response
                    template_size = struct.unpack('<I', result[:4])[0]
                    if template_size > 0 and len(result) >= 4 + template_size:
                        return result[4:4+template_size]
            except Exception as e:
                logging.debug(f"Raw face template command failed for UID {uid}: {e}")
            
            # Method 3: Try read_with_buffer with different commands
            for cmd in [1503, 1504, 1505]:
                try:
                    result = conn.read_with_buffer(cmd, uid)
                    if result and len(result) > 0:
                        return result
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logging.debug(f"Error getting face template for UID {uid}: {e}")
            return None
    
    def set_face_template_raw(self, conn, uid: int, template_data: bytes) -> bool:
        """Set face template using raw command protocol"""
        try:
            # Method 1: Try standard method if available
            if hasattr(conn, 'set_face_template'):
                try:
                    result = conn.set_face_template(uid=uid, template=template_data)
                    if result:
                        return True
                except Exception as e:
                    logging.debug(f"Standard set_face_template failed for UID {uid}: {e}")
            
            # Method 2: Use raw command protocol
            try:
                # Prepare command data: UID + template size + template data
                template_size = len(template_data)
                command_data = struct.pack('<II', uid, template_size) + template_data
                result = conn.send_command(self.CMD_SET_FACE_TEMPLATE, command_data)
                return result is not None
            except Exception as e:
                logging.debug(f"Raw set face template command failed for UID {uid}: {e}")
            
            return False
            
        except Exception as e:
            logging.error(f"Error setting face template for UID {uid}: {e}")
            return False
    
    def get_user_photo_raw(self, conn, uid: int) -> Optional[bytes]:
        """Get user photo using raw command protocol"""
        try:
            # Method 1: Try standard method if available
            if hasattr(conn, 'get_user_photo'):
                try:
                    result = conn.get_user_photo(uid=uid)
                    if result:
                        return result
                except Exception as e:
                    logging.debug(f"Standard get_user_photo failed for UID {uid}: {e}")
            
            # Method 2: Use raw command protocol
            try:
                command_data = struct.pack('<I', uid)
                result = conn.send_command(self.CMD_GET_USER_PHOTO, command_data)
                if result and len(result) > 4:
                    photo_size = struct.unpack('<I', result[:4])[0]
                    if photo_size > 0 and len(result) >= 4 + photo_size:
                        return result[4:4+photo_size]
            except Exception as e:
                logging.debug(f"Raw photo command failed for UID {uid}: {e}")
            
            # Method 3: Try alternative commands
            for cmd in [1505, 1506]:
                try:
                    result = conn.read_with_buffer(cmd, uid)
                    if result and len(result) > 0:
                        return result
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logging.debug(f"Error getting photo for UID {uid}: {e}")
            return None
    
    def set_user_photo_raw(self, conn, uid: int, photo_data: bytes) -> bool:
        """Set user photo using raw command protocol"""
        try:
            # Method 1: Try standard method if available
            if hasattr(conn, 'set_user_photo'):
                try:
                    result = conn.set_user_photo(uid=uid, photo=photo_data)
                    if result:
                        return True
                except Exception as e:
                    logging.debug(f"Standard set_user_photo failed for UID {uid}: {e}")
            
            # Method 2: Use raw command protocol
            try:
                photo_size = len(photo_data)
                command_data = struct.pack('<II', uid, photo_size) + photo_data
                result = conn.send_command(self.CMD_SET_USER_PHOTO, command_data)
                return result is not None
            except Exception as e:
                logging.debug(f"Raw set photo command failed for UID {uid}: {e}")
            
            return False
            
        except Exception as e:
            logging.error(f"Error setting photo for UID {uid}: {e}")
            return False
    
    def get_device_face_data(self, conn, ip_address: str, limit_users: int = None) -> Dict[str, Any]:
        """Get face templates and photos from device with optional user limit"""
        try:
            logging.info(f"Fetching face data from {ip_address}...")
            start_time = time.time()
            
            # Get users
            users = conn.get_users() or []
            if limit_users:
                users = users[:limit_users]
                logging.info(f"Limited to first {limit_users} users")
            
            user_dict = {user.user_id: user for user in users}
            logging.info(f"Processing {len(users)} users for face data")
            
            # Get face templates
            face_templates = {}
            face_count = 0
            
            # Check device face capability
            try:
                if hasattr(conn, 'faces'):
                    device_face_count = conn.faces
                    logging.info(f"Device reports {device_face_count} face templates")
            except:
                pass
            
            # Get face templates for each user
            for i, user in enumerate(users):
                try:
                    if i % 50 == 0:  # Progress update every 50 users
                        logging.info(f"Processing face templates: {i}/{len(users)}")
                    
                    face_template = self.get_face_template_raw(conn, user.uid)
                    if face_template:
                        face_templates[user.user_id] = face_template
                        face_count += 1
                        
                except Exception as e:
                    logging.debug(f"Error getting face template for user {user.user_id}: {e}")
                    continue
            
            face_time = time.time() - start_time
            logging.info(f"Found {face_count} face templates in {face_time:.2f} seconds")
            
            # Get user photos
            user_photos = {}
            photo_count = 0
            photo_start = time.time()
            
            for i, user in enumerate(users):
                try:
                    if i % 50 == 0:  # Progress update every 50 users
                        logging.info(f"Processing photos: {i}/{len(users)}")
                    
                    photo = self.get_user_photo_raw(conn, user.uid)
                    if photo:
                        user_photos[user.user_id] = photo
                        photo_count += 1
                        
                except Exception as e:
                    logging.debug(f"Error getting photo for user {user.user_id}: {e}")
                    continue
            
            photo_time = time.time() - photo_start
            total_time = time.time() - start_time
            
            logging.info(f"Found {photo_count} user photos in {photo_time:.2f} seconds")
            logging.info(f"Total face data fetch time: {total_time:.2f} seconds")
            
            return {
                'users': user_dict,
                'face_templates': face_templates,
                'user_photos': user_photos,
                'face_count': face_count,
                'photo_count': photo_count,
                'fetch_time': total_time
            }
            
        except Exception as e:
            logging.error(f"Error fetching face data from {ip_address}: {e}")
            return {
                'users': {},
                'face_templates': {},
                'user_photos': {},
                'face_count': 0,
                'photo_count': 0,
                'fetch_time': 0
            }
    
    def sync_face_data_between_devices(self, source_conn, target_conn, source_data, target_data, 
                                     source_ip: str, target_ip: str) -> Dict[str, int]:
        """Sync face templates and photos between devices"""
        
        face_synced = 0
        photos_synced = 0
        
        source_users = source_data['users']
        target_users = target_data['users']
        source_faces = source_data['face_templates']
        source_photos = source_data['user_photos']
        
        # Find users that exist on both devices but missing face data on target
        common_users = set(source_users.keys()) & set(target_users.keys())
        
        logging.info(f"Syncing face data for {len(common_users)} common users from {source_ip} to {target_ip}")
        
        for user_id in common_users:
            source_user = source_users[user_id]
            target_user = target_users[user_id]
            
            # Sync face template if available on source but not on target
            if (user_id in source_faces and 
                user_id not in target_data['face_templates']):
                try:
                    if self.set_face_template_raw(target_conn, target_user.uid, source_faces[user_id]):
                        face_synced += 1
                        logging.info(f"Synced face template for user {user_id}")
                    else:
                        logging.warning(f"Failed to sync face template for user {user_id}")
                except Exception as e:
                    logging.error(f"Error syncing face template for user {user_id}: {e}")
            
            # Sync photo if available on source but not on target
            if (user_id in source_photos and 
                user_id not in target_data['user_photos']):
                try:
                    if self.set_user_photo_raw(target_conn, target_user.uid, source_photos[user_id]):
                        photos_synced += 1
                        logging.info(f"Synced photo for user {user_id}")
                    else:
                        logging.warning(f"Failed to sync photo for user {user_id}")
                except Exception as e:
                    logging.error(f"Error syncing photo for user {user_id}: {e}")
        
        return {
            'face_templates_synced': face_synced,
            'photos_synced': photos_synced
        }
    
    def test_face_sync(self, device_ips: List[str], limit_users: int = 100) -> Dict[str, Any]:
        """Test face template and photo sync between devices"""
        
        logging.info(f"Starting face sync test with {len(device_ips)} devices (limit: {limit_users} users)")
        start_time = time.time()
        
        # Connect to devices
        device_connections = {}
        for ip in device_ips:
            conn = self.connect_to_device(ip)
            if conn:
                device_connections[ip] = conn
        
        if len(device_connections) < 2:
            return {
                'success': False,
                'message': f'Need at least 2 connected devices, got {len(device_connections)}'
            }
        
        # Get face data from all devices
        device_face_data = {}
        for ip, conn in device_connections.items():
            device_face_data[ip] = self.get_device_face_data(conn, ip, limit_users)
        
        # Find primary device (most face templates + photos)
        primary_ip = max(device_face_data.keys(), 
                        key=lambda ip: device_face_data[ip]['face_count'] + device_face_data[ip]['photo_count'])
        
        primary_data = device_face_data[primary_ip]
        logging.info(f"Primary device: {primary_ip} with {primary_data['face_count']} face templates "
                    f"and {primary_data['photo_count']} photos")
        
        # Sync from primary to other devices
        sync_results = {}
        total_face_synced = 0
        total_photos_synced = 0
        
        for target_ip, target_data in device_face_data.items():
            if target_ip == primary_ip:
                continue
            
            try:
                result = self.sync_face_data_between_devices(
                    device_connections[primary_ip], device_connections[target_ip],
                    primary_data, target_data,
                    primary_ip, target_ip
                )
                
                sync_results[target_ip] = result
                total_face_synced += result['face_templates_synced']
                total_photos_synced += result['photos_synced']
                
                logging.info(f"Synced {result['face_templates_synced']} face templates and "
                           f"{result['photos_synced']} photos to {target_ip}")
                
            except Exception as e:
                logging.error(f"Error syncing face data to {target_ip}: {e}")
                sync_results[target_ip] = {'face_templates_synced': 0, 'photos_synced': 0}
        
        # Disconnect all devices
        for ip, conn in device_connections.items():
            try:
                conn.disconnect()
                logging.info(f"Disconnected from {ip}")
            except Exception as e:
                logging.warning(f"Error disconnecting from {ip}: {e}")
        
        total_time = time.time() - start_time
        
        return {
            'success': True,
            'primary_device': primary_ip,
            'total_face_synced': total_face_synced,
            'total_photos_synced': total_photos_synced,
            'sync_time': total_time,
            'device_results': sync_results,
            'device_data': {ip: {
                'face_count': data['face_count'],
                'photo_count': data['photo_count'],
                'user_count': len(data['users'])
            } for ip, data in device_face_data.items()}
        }


def test_enhanced_face_sync():
    """Test the enhanced face sync"""
    device_ips = ["192.168.41.212", "192.168.41.205"]
    
    face_sync = EnhancedFaceSync()
    
    print("Enhanced Face Template and Photo Sync Test")
    print("=" * 60)
    print(f"Testing with devices: {device_ips}")
    print("Limiting to first 100 users for quick testing")
    print()
    
    result = face_sync.test_face_sync(device_ips, limit_users=100)
    
    print("\nFace Sync Results:")
    print("=" * 40)
    print(f"Success: {result['success']}")
    
    if result['success']:
        print(f"Primary Device: {result['primary_device']}")
        print(f"Total Face Templates Synced: {result['total_face_synced']}")
        print(f"Total Photos Synced: {result['total_photos_synced']}")
        print(f"Total Sync Time: {result['sync_time']:.2f} seconds")
        
        print("\nDevice Data Summary:")
        for ip, data in result['device_data'].items():
            print(f"  {ip}: {data['user_count']} users, {data['face_count']} faces, {data['photo_count']} photos")
        
        print("\nSync Results by Device:")
        for ip, sync_data in result['device_results'].items():
            print(f"  {ip}: {sync_data['face_templates_synced']} faces, {sync_data['photos_synced']} photos")
    else:
        print(f"Error: {result['message']}")


if __name__ == "__main__":
    test_enhanced_face_sync()