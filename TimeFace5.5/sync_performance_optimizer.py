#!/usr/bin/env python3
"""
Sync Performance Optimizer - Optimized version of device sync with progress tracking
"""

import logging
import time
import threading
from typing import Dict, List, Optional, Any
from zk import ZK
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync_performance.log'),
        logging.StreamHandler()
    ]
)

class OptimizedDeviceSync:
    """Optimized device sync with parallel processing and progress tracking"""
    
    def __init__(self, max_workers=3):
        self.max_workers = max_workers
        self.progress_callback = None
        
    def set_progress_callback(self, callback):
        """Set callback function for progress updates"""
        self.progress_callback = callback
        
    def update_progress(self, message, percentage=None):
        """Update progress with message and optional percentage"""
        if self.progress_callback:
            self.progress_callback(message, percentage)
        else:
            if percentage is not None:
                print(f"[{percentage:3.0f}%] {message}")
            else:
                print(f"[INFO] {message}")
    
    def connect_to_device(self, ip_address: str, port: int = 4370, timeout: int = 15) -> Optional[Any]:
        """Connect to device with shorter timeout for faster failure detection"""
        try:
            self.update_progress(f"Connecting to {ip_address}...")
            zk = ZK(ip_address, port=port, timeout=timeout, ommit_ping=True)
            conn = zk.connect()
            self.update_progress(f"Connected to {ip_address}")
            return conn
        except Exception as e:
            self.update_progress(f"Failed to connect to {ip_address}: {e}")
            return None
    
    def get_device_summary(self, conn, ip_address: str) -> Dict[str, Any]:
        """Get device summary with essential data only"""
        try:
            start_time = time.time()
            
            # Get users
            users = conn.get_users() or []
            user_count = len(users)
            
            # Get fingerprint templates count only (not the actual data)
            try:
                templates = conn.get_templates() or []
                template_count = len(templates)
            except:
                template_count = 0
            
            # Get face count if available
            face_count = 0
            try:
                if hasattr(conn, 'faces'):
                    face_count = conn.faces
            except:
                pass
            
            fetch_time = time.time() - start_time
            
            return {
                'ip_address': ip_address,
                'users': {user.user_id: user for user in users},
                'user_count': user_count,
                'template_count': template_count,
                'face_count': face_count,
                'total_items': user_count + template_count + face_count,
                'fetch_time': fetch_time
            }
            
        except Exception as e:
            logging.error(f"Error getting summary from {ip_address}: {e}")
            return {
                'ip_address': ip_address,
                'users': {},
                'user_count': 0,
                'template_count': 0,
                'face_count': 0,
                'total_items': 0,
                'fetch_time': 0,
                'error': str(e)
            }
    
    def get_detailed_device_data(self, conn, ip_address: str, user_ids: List[str] = None) -> Dict[str, Any]:
        """Get detailed data for specific users only"""
        try:
            self.update_progress(f"Fetching detailed data from {ip_address}...")
            
            # Get all users first
            all_users = conn.get_users() or []
            user_dict = {user.user_id: user for user in all_users}
            
            # Filter users if specific IDs provided
            if user_ids:
                filtered_users = {uid: user for uid, user in user_dict.items() if uid in user_ids}
            else:
                filtered_users = user_dict
            
            # Get templates for filtered users only
            all_templates = conn.get_templates() or []
            uid_to_user_id = {user.uid: user.user_id for user in all_users}
            
            user_templates = {}
            for template in all_templates:
                user_id = uid_to_user_id.get(template.uid)
                if user_id and user_id in filtered_users:
                    if user_id not in user_templates:
                        user_templates[user_id] = []
                    user_templates[user_id].append(template)
            
            # Get face templates for filtered users
            face_templates = {}
            for user in filtered_users.values():
                try:
                    face_template = self.get_face_template(conn, user)
                    if face_template:
                        face_templates[user.user_id] = face_template
                except:
                    continue
            
            # Get photos for filtered users
            user_photos = {}
            for user in filtered_users.values():
                try:
                    photo = self.get_user_photo(conn, user.uid)
                    if photo:
                        user_photos[user.user_id] = photo
                except:
                    continue
            
            return {
                'users': filtered_users,
                'fingerprint_templates': user_templates,
                'face_templates': face_templates,
                'user_photos': user_photos
            }
            
        except Exception as e:
            logging.error(f"Error getting detailed data from {ip_address}: {e}")
            return {
                'users': {},
                'fingerprint_templates': {},
                'face_templates': {},
                'user_photos': {}
            }
    
    def get_face_template(self, conn, user) -> Optional[Any]:
        """Get face template for user"""
        try:
            if hasattr(conn, 'get_face_template'):
                return conn.get_face_template(uid=user.uid)
            return None
        except:
            return None
    
    def get_user_photo(self, conn, user_uid: int) -> Optional[Any]:
        """Get user photo"""
        try:
            if hasattr(conn, 'get_user_photo'):
                return conn.get_user_photo(uid=user_uid)
            return None
        except:
            return None
    
    def optimized_sync(self, device_ips: List[str]) -> Dict[str, Any]:
        """Optimized sync with parallel processing"""
        start_time = time.time()
        
        self.update_progress("Starting optimized device sync...", 0)
        
        # Step 1: Connect to all devices in parallel
        device_connections = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ip = {
                executor.submit(self.connect_to_device, ip): ip 
                for ip in device_ips
            }
            
            for future in as_completed(future_to_ip):
                ip = future_to_ip[future]
                try:
                    conn = future.result()
                    if conn:
                        device_connections[ip] = conn
                except Exception as e:
                    logging.error(f"Connection failed for {ip}: {e}")
        
        if not device_connections:
            return {'success': False, 'message': 'No devices could be connected'}
        
        self.update_progress(f"Connected to {len(device_connections)} devices", 20)
        
        # Step 2: Get device summaries in parallel
        device_summaries = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ip = {
                executor.submit(self.get_device_summary, conn, ip): ip 
                for ip, conn in device_connections.items()
            }
            
            for future in as_completed(future_to_ip):
                ip = future_to_ip[future]
                try:
                    summary = future.result()
                    device_summaries[ip] = summary
                    self.update_progress(f"Got summary from {ip}: {summary['user_count']} users")
                except Exception as e:
                    logging.error(f"Summary failed for {ip}: {e}")
        
        self.update_progress("Device summaries completed", 40)
        
        # Step 3: Determine primary device and sync strategy
        if not device_summaries:
            return {'success': False, 'message': 'No device summaries available'}
        
        primary_ip = max(device_summaries.keys(), 
                        key=lambda ip: device_summaries[ip]['total_items'])
        
        primary_summary = device_summaries[primary_ip]
        self.update_progress(f"Primary device: {primary_ip} ({primary_summary['total_items']} items)", 50)
        
        # Step 4: Identify users to sync
        primary_users = set(primary_summary['users'].keys())
        sync_results = {}
        
        for target_ip, target_summary in device_summaries.items():
            if target_ip == primary_ip:
                continue
                
            target_users = set(target_summary['users'].keys())
            missing_users = primary_users - target_users
            
            if missing_users:
                self.update_progress(f"Need to sync {len(missing_users)} users to {target_ip}")
                
                # Get detailed data for missing users only
                primary_conn = device_connections[primary_ip]
                target_conn = device_connections[target_ip]
                
                detailed_data = self.get_detailed_device_data(
                    primary_conn, primary_ip, list(missing_users)
                )
                
                # Sync the missing users
                result = self.sync_missing_users(
                    target_conn, detailed_data, target_summary, target_ip
                )
                
                sync_results[target_ip] = result
            else:
                sync_results[target_ip] = {'users_synced': 0, 'templates_synced': 0}
        
        self.update_progress("Sync operations completed", 90)
        
        # Step 5: Disconnect all devices
        for ip, conn in device_connections.items():
            try:
                conn.disconnect()
            except Exception as e:
                logging.warning(f"Error disconnecting from {ip}: {e}")
        
        total_time = time.time() - start_time
        total_users = sum(r['users_synced'] for r in sync_results.values())
        total_templates = sum(r['templates_synced'] for r in sync_results.values())
        
        self.update_progress("Sync completed successfully!", 100)
        
        return {
            'success': True,
            'primary_device': primary_ip,
            'total_users_synced': total_users,
            'total_templates_synced': total_templates,
            'sync_time': total_time,
            'device_results': sync_results
        }
    
    def sync_missing_users(self, target_conn, detailed_data, target_summary, target_ip):
        """Sync missing users to target device"""
        users_synced = 0
        templates_synced = 0
        
        existing_uids = {user.uid for user in target_summary['users'].values()}
        max_uid = max(existing_uids) if existing_uids else 0
        
        for user_id, user in detailed_data['users'].items():
            try:
                # Assign new UID if needed
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
                
                # Add templates if available
                if user_id in detailed_data['fingerprint_templates']:
                    try:
                        templates = detailed_data['fingerprint_templates'][user_id]
                        target_conn.save_user_template(user=new_uid, fingers=templates)
                        templates_synced += len(templates)
                    except Exception as e:
                        logging.warning(f"Failed to sync fingerprints for {user_id}: {e}")
                
                self.update_progress(f"Synced user {user_id} to {target_ip}")
                
            except Exception as e:
                logging.error(f"Error syncing user {user_id} to {target_ip}: {e}")
        
        return {'users_synced': users_synced, 'templates_synced': templates_synced}


def test_optimized_sync():
    """Test the optimized sync"""
    device_ips = ["192.168.41.212", "192.168.41.205"]
    
    def progress_callback(message, percentage=None):
        if percentage is not None:
            print(f"[{percentage:3.0f}%] {message}")
        else:
            print(f"[INFO] {message}")
    
    sync_manager = OptimizedDeviceSync(max_workers=2)
    sync_manager.set_progress_callback(progress_callback)
    
    print("Starting Optimized Device Sync Test")
    print("=" * 50)
    
    result = sync_manager.optimized_sync(device_ips)
    
    print("\nSync Results:")
    print(f"Success: {result['success']}")
    if result['success']:
        print(f"Primary Device: {result['primary_device']}")
        print(f"Users Synced: {result['total_users_synced']}")
        print(f"Templates Synced: {result['total_templates_synced']}")
        print(f"Total Time: {result['sync_time']:.2f} seconds")


if __name__ == "__main__":
    test_optimized_sync()