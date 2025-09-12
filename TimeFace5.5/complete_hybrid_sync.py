#!/usr/bin/env python3
"""
Complete Hybrid Sync Solution
Successfully combines pyzk (users/fingerprints) + fpmachine (faces/photos)
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('complete_hybrid_sync.log'),
        logging.StreamHandler()
    ]
)

class CompleteHybridSync:
    """Complete hybrid sync solution using both pyzk and fpmachine"""
    
    def __init__(self):
        self.pyzk_connections = {}
        self.fpmachine_connections = {}
    
    def connect_pyzk(self, ip_address: str) -> Optional[Any]:
        """Connect using pyzk library for users/fingerprints"""
        try:
            from zk import ZK
            zk = ZK(ip_address, port=4370, timeout=15, ommit_ping=True)
            conn = zk.connect()
            if conn:
                self.pyzk_connections[ip_address] = conn
                logging.info(f"pyzk connected to {ip_address}")
                return conn
        except Exception as e:
            logging.error(f"pyzk connection failed for {ip_address}: {e}")
        return None
    
    def connect_fpmachine(self, ip_address: str) -> Optional[Any]:
        """Connect using fpmachine library for faces/photos"""
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
    
    def sync_users_and_fingerprints(self, source_ip: str, target_ip: str) -> Dict[str, int]:
        """Sync users and fingerprints using pyzk (proven working method)"""
        
        if source_ip not in self.pyzk_connections or target_ip not in self.pyzk_connections:
            logging.error("Both devices must be connected via pyzk for user/fingerprint sync")
            return {'users_synced': 0, 'templates_synced': 0}
        
        source_conn = self.pyzk_connections[source_ip]
        target_conn = self.pyzk_connections[target_ip]
        
        logging.info(f"Syncing users and fingerprints from {source_ip} to {target_ip}")
        
        # Get users from both devices
        source_users = source_conn.get_users() or []
        target_users = target_conn.get_users() or []
        
        source_user_dict = {user.user_id: user for user in source_users}
        target_user_dict = {user.user_id: user for user in target_users}
        
        # Get fingerprint templates
        source_templates = source_conn.get_templates() or []
        
        # Group templates by user
        source_uid_to_user_id = {user.uid: user.user_id for user in source_users}
        user_templates = {}
        for template in source_templates:
            user_id = source_uid_to_user_id.get(template.uid)
            if user_id:
                if user_id not in user_templates:
                    user_templates[user_id] = []
                user_templates[user_id].append(template)
        
        # Find users to sync
        users_to_add = [user for user_id, user in source_user_dict.items() 
                       if user_id not in target_user_dict]
        
        users_synced = 0
        templates_synced = 0
        
        # Get existing UIDs on target to avoid conflicts
        existing_uids = {user.uid for user in target_users}
        max_uid = max(existing_uids) if existing_uids else 0
        
        for user in users_to_add:
            try:
                # Assign UID
                if user.uid not in existing_uids:
                    new_uid = user.uid
                else:
                    max_uid += 1
                    new_uid = max_uid
                
                # Add user
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
                
                # Add fingerprint templates
                if user.user_id in user_templates:
                    try:
                        templates = user_templates[user.user_id]
                        result = target_conn.save_user_template(user=new_uid, fingers=templates)
                        if result is not False:
                            templates_synced += len(templates)
                    except Exception as e:
                        logging.warning(f"Failed to sync fingerprints for user {user.user_id}: {e}")
                
                logging.info(f"Synced user {user.user_id} ({user.name}) with {len(user_templates.get(user.user_id, []))} templates")
                
            except Exception as e:
                logging.error(f"Error syncing user {user.user_id}: {e}")
        
        return {'users_synced': users_synced, 'templates_synced': templates_synced}
    
    def get_users_with_face_data(self, ip_address: str) -> Dict[str, Dict[str, Any]]:
        """Get users with face templates and photos using fpmachine"""
        
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
    
    def sync_face_and_photos(self, source_ip: str, target_ip: str) -> Dict[str, int]:
        """Sync face templates and photos using fpmachine"""
        
        if source_ip not in self.fpmachine_connections or target_ip not in self.fpmachine_connections:
            logging.error("Both devices must be connected via fpmachine for face sync")
            return {'face_templates_synced': 0, 'photos_synced': 0, 'errors': 0}
        
        source_dev = self.fpmachine_connections[source_ip]
        target_dev = self.fpmachine_connections[target_ip]
        
        # Get users with face data from source
        source_face_data = self.get_users_with_face_data(source_ip)
        
        if not source_face_data:
            logging.info(f"No face data found on source device {source_ip}")
            return {'face_templates_synced': 0, 'photos_synced': 0, 'errors': 0}
        
        logging.info(f"Syncing face data from {source_ip} to {target_ip} for {len(source_face_data)} users")
        
        results = {'face_templates_synced': 0, 'photos_synced': 0, 'errors': 0}
        
        for user_id, face_data in source_face_data.items():
            try:
                # Sync face template
                if face_data['face_template']:
                    try:
                        success = target_dev.set_user_face(str(user_id), face_data['face_template'])
                        if success:
                            results['face_templates_synced'] += 1
                            logging.info(f"✓ Synced face template for user {user_id} ({face_data['user_name']})")
                        else:
                            logging.warning(f"✗ Failed to sync face template for user {user_id}")
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
                            logging.info(f"✓ Synced photo for user {user_id} ({face_data['user_name']})")
                        else:
                            logging.warning(f"✗ Failed to sync photo for user {user_id}")
                            results['errors'] += 1
                    except Exception as e:
                        logging.error(f"Error syncing photo for user {user_id}: {e}")
                        results['errors'] += 1
                        
            except Exception as e:
                logging.error(f"Error syncing data for user {user_id}: {e}")
                results['errors'] += 1
        
        return results
    
    def complete_sync(self, device_ips: List[str]) -> Dict[str, Any]:
        """Perform complete hybrid sync of all data types"""
        
        logging.info(f"Starting complete hybrid sync with {len(device_ips)} devices")
        start_time = time.time()
        
        if len(device_ips) < 2:
            return {'success': False, 'error': 'Need at least 2 devices'}
        
        # Step 1: Connect to all devices with both libraries
        logging.info("Step 1: Connecting to devices...")
        for ip in device_ips:
            self.connect_pyzk(ip)
            self.connect_fpmachine(ip)
        
        # Check connections
        pyzk_connected = list(self.pyzk_connections.keys())
        fpmachine_connected = list(self.fpmachine_connections.keys())
        
        if len(pyzk_connected) < 2:
            return {'success': False, 'error': f'Need at least 2 pyzk connections, got {len(pyzk_connected)}'}
        
        if len(fpmachine_connected) < 2:
            return {'success': False, 'error': f'Need at least 2 fpmachine connections, got {len(fpmachine_connected)}'}
        
        # Step 2: Determine primary device (most users)
        logging.info("Step 2: Determining primary device...")
        device_user_counts = {}
        
        for ip in pyzk_connected:
            try:
                users = self.pyzk_connections[ip].get_users() or []
                device_user_counts[ip] = len(users)
            except:
                device_user_counts[ip] = 0
        
        primary_ip = max(device_user_counts.keys(), key=lambda ip: device_user_counts[ip])
        logging.info(f"Primary device: {primary_ip} with {device_user_counts[primary_ip]} users")
        
        # Step 3: Sync users and fingerprints
        logging.info("Step 3: Syncing users and fingerprints...")
        user_sync_results = {}
        total_users_synced = 0
        total_templates_synced = 0
        
        for target_ip in pyzk_connected:
            if target_ip != primary_ip:
                result = self.sync_users_and_fingerprints(primary_ip, target_ip)
                user_sync_results[target_ip] = result
                total_users_synced += result['users_synced']
                total_templates_synced += result['templates_synced']
        
        # Step 4: Sync face templates and photos
        logging.info("Step 4: Syncing face templates and photos...")
        face_sync_results = {}
        total_face_synced = 0
        total_photos_synced = 0
        total_face_errors = 0
        
        for target_ip in fpmachine_connected:
            if target_ip != primary_ip:
                result = self.sync_face_and_photos(primary_ip, target_ip)
                face_sync_results[target_ip] = result
                total_face_synced += result['face_templates_synced']
                total_photos_synced += result['photos_synced']
                total_face_errors += result['errors']
        
        # Step 5: Cleanup
        self.disconnect_all()
        
        total_time = time.time() - start_time
        
        return {
            'success': True,
            'total_time': total_time,
            'primary_device': primary_ip,
            'device_user_counts': device_user_counts,
            'user_sync_results': user_sync_results,
            'face_sync_results': face_sync_results,
            'totals': {
                'users_synced': total_users_synced,
                'fingerprint_templates_synced': total_templates_synced,
                'face_templates_synced': total_face_synced,
                'photos_synced': total_photos_synced,
                'face_sync_errors': total_face_errors
            }
        }
    
    def disconnect_all(self):
        """Disconnect from all devices"""
        for ip, conn in self.pyzk_connections.items():
            try:
                conn.disconnect()
                logging.info(f"Disconnected pyzk from {ip}")
            except Exception as e:
                logging.warning(f"Error disconnecting pyzk from {ip}: {e}")
        
        for ip, dev in self.fpmachine_connections.items():
            try:
                dev.disconnect()
                logging.info(f"Disconnected fpmachine from {ip}")
            except Exception as e:
                logging.warning(f"Error disconnecting fpmachine from {ip}: {e}")
        
        self.pyzk_connections.clear()
        self.fpmachine_connections.clear()


def test_complete_hybrid_sync():
    """Test the complete hybrid sync solution"""
    device_ips = ["192.168.41.212", "192.168.41.205"]
    
    print("Complete Hybrid Sync Test")
    print("=" * 50)
    print("This solution syncs ALL data types:")
    print("  ✓ Users (pyzk)")
    print("  ✓ Fingerprint templates (pyzk)")
    print("  ✓ Face templates (fpmachine)")
    print("  ✓ Photos (fpmachine)")
    print()
    
    hybrid_sync = CompleteHybridSync()
    
    try:
        result = hybrid_sync.complete_sync(device_ips)
        
        print("Complete Sync Results:")
        print("=" * 30)
        print(f"Success: {result['success']}")
        
        if result['success']:
            print(f"Total Time: {result['total_time']:.2f} seconds")
            print(f"Primary Device: {result['primary_device']}")
            
            totals = result['totals']
            print(f"\nSync Summary:")
            print(f"  Users Synced: {totals['users_synced']}")
            print(f"  Fingerprint Templates: {totals['fingerprint_templates_synced']}")
            print(f"  Face Templates: {totals['face_templates_synced']}")
            print(f"  Photos: {totals['photos_synced']}")
            print(f"  Face Sync Errors: {totals['face_sync_errors']}")
            
            print(f"\nDevice User Counts:")
            for ip, count in result['device_user_counts'].items():
                marker = " (PRIMARY)" if ip == result['primary_device'] else ""
                print(f"  {ip}: {count} users{marker}")
            
            print(f"\nDetailed Results:")
            for target_ip, user_result in result['user_sync_results'].items():
                face_result = result['face_sync_results'].get(target_ip, {})
                print(f"  {target_ip}:")
                print(f"    Users: {user_result['users_synced']}")
                print(f"    Fingerprints: {user_result['templates_synced']}")
                print(f"    Face Templates: {face_result.get('face_templates_synced', 0)}")
                print(f"    Photos: {face_result.get('photos_synced', 0)}")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        
    except Exception as e:
        print(f"Error in complete sync: {e}")
        logging.exception("Detailed error:")


if __name__ == "__main__":
    test_complete_hybrid_sync()