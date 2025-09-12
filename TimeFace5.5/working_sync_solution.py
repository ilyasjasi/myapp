#!/usr/bin/env python3
"""
Working Sync Solution - Focus on what works: Users and Fingerprint Templates
Face templates require different approach due to pyzk library limitations
"""

import logging
import time
from typing import Dict, List, Optional, Any
from zk import ZK

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('working_sync.log'),
        logging.StreamHandler()
    ]
)

class WorkingSyncSolution:
    """Working sync solution that focuses on users and fingerprint templates"""
    
    def __init__(self):
        self.sync_in_progress = set()
    
    def connect_to_device(self, ip_address: str, port: int = 4370, timeout: int = 15) -> Optional[Any]:
        """Connect to device"""
        try:
            logging.info(f"Connecting to {ip_address}...")
            zk = ZK(ip_address, port=port, timeout=timeout, ommit_ping=True)
            conn = zk.connect()
            logging.info(f"Connected to {ip_address}")
            return conn
        except Exception as e:
            logging.error(f"Failed to connect to {ip_address}: {e}")
            return None
    
    def get_device_data_optimized(self, conn, ip_address: str, limit_users: int = None) -> Dict[str, Any]:
        """Get device data with optimizations for speed"""
        try:
            logging.info(f"Fetching data from {ip_address}...")
            start_time = time.time()
            
            # Get users
            all_users = conn.get_users() or []
            if limit_users:
                users = all_users[:limit_users]
                logging.info(f"Limited to first {limit_users} users")
            else:
                users = all_users
            
            user_dict = {user.user_id: user for user in users}
            user_fetch_time = time.time()
            logging.info(f"Found {len(users)} users in {user_fetch_time - start_time:.2f} seconds")
            
            # Get fingerprint templates
            all_templates = conn.get_templates() or []
            uid_to_user_id = {user.uid: user.user_id for user in users}
            
            user_templates = {}
            template_count = 0
            
            for template in all_templates:
                user_id = uid_to_user_id.get(template.uid)
                if user_id:
                    if user_id not in user_templates:
                        user_templates[user_id] = []
                    user_templates[user_id].append(template)
                    template_count += 1
            
            template_fetch_time = time.time()
            logging.info(f"Found {template_count} fingerprint templates for {len(user_templates)} users in {template_fetch_time - user_fetch_time:.2f} seconds")
            
            # Check face template capability (but don't try to retrieve them)
            face_capability = {
                'face_version': 0,
                'face_function_enabled': False,
                'reported_face_count': 0
            }
            
            try:
                if hasattr(conn, 'get_face_version'):
                    face_capability['face_version'] = conn.get_face_version()
                if hasattr(conn, 'get_face_fun_on'):
                    face_capability['face_function_enabled'] = bool(conn.get_face_fun_on())
                if hasattr(conn, 'faces'):
                    face_capability['reported_face_count'] = conn.faces
            except Exception as e:
                logging.debug(f"Error checking face capability: {e}")
            
            total_time = time.time() - start_time
            logging.info(f"Completed data fetch from {ip_address} in {total_time:.2f} seconds")
            
            return {
                'users': user_dict,
                'fingerprint_templates': user_templates,
                'face_capability': face_capability,
                'user_count': len(users),
                'template_count': template_count,
                'fetch_time': total_time
            }
            
        except Exception as e:
            logging.error(f"Error fetching data from {ip_address}: {e}")
            return {
                'users': {},
                'fingerprint_templates': {},
                'face_capability': {},
                'user_count': 0,
                'template_count': 0,
                'fetch_time': 0
            }
    
    def sync_users_and_templates(self, source_conn, target_conn, source_data, target_data, 
                                source_ip: str, target_ip: str) -> Dict[str, int]:
        """Sync users and fingerprint templates between devices"""
        
        users_synced = 0
        templates_synced = 0
        
        source_users = source_data['users']
        target_users = target_data['users']
        source_templates = source_data['fingerprint_templates']
        
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
                    # Assign UID
                    if user.uid not in existing_uids:
                        new_uid = user.uid
                    else:
                        max_uid += 1
                        new_uid = max_uid
                    
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
                    
                    # Add fingerprint templates if available
                    if user.user_id in source_templates:
                        try:
                            templates = source_templates[user.user_id]
                            result = target_conn.save_user_template(user=new_uid, fingers=templates)
                            if result is not False:
                                templates_synced += len(templates)
                                logging.info(f"Synced {len(templates)} fingerprint templates for user {user.user_id}")
                        except Exception as e:
                            logging.warning(f"Failed to sync fingerprints for user {user.user_id}: {e}")
                    
                    logging.info(f"Added user {user.user_id} to {target_ip} with UID {new_uid}")
                    
                except Exception as e:
                    logging.error(f"Error adding user {user.user_id} to {target_ip}: {e}")
        
        # Add missing templates for existing users
        for user_id, user in source_users.items():
            if user_id in target_users:
                target_user = target_users[user_id]
                
                # Check if user has templates on source but not on target
                if (user_id in source_templates and 
                    user_id not in target_data['fingerprint_templates']):
                    try:
                        templates = source_templates[user_id]
                        result = target_conn.save_user_template(user=target_user.uid, fingers=templates)
                        if result is not False:
                            templates_synced += len(templates)
                            logging.info(f"Added {len(templates)} fingerprint templates for existing user {user_id}")
                    except Exception as e:
                        logging.warning(f"Failed to add templates for user {user_id}: {e}")
        
        return {
            'users_synced': users_synced,
            'templates_synced': templates_synced
        }
    
    def sync_devices(self, device_ips: List[str], limit_users: int = None) -> Dict[str, Any]:
        """Sync devices with working solution"""
        
        logging.info(f"Starting device sync with {len(device_ips)} devices")
        if limit_users:
            logging.info(f"Limited to first {limit_users} users per device")
        
        start_time = time.time()
        device_connections = {}
        
        try:
            # Connect to devices
            for ip in device_ips:
                conn = self.connect_to_device(ip)
                if conn:
                    device_connections[ip] = conn
            
            if len(device_connections) < 2:
                return {
                    'success': False,
                    'message': f'Need at least 2 connected devices, got {len(device_connections)}'
                }
            
            # Get device data
            device_data = {}
            for ip, conn in device_connections.items():
                device_data[ip] = self.get_device_data_optimized(conn, ip, limit_users)
            
            # Find primary device (most users + templates)
            primary_ip = max(device_data.keys(), 
                           key=lambda ip: device_data[ip]['user_count'] + device_data[ip]['template_count'])
            
            primary_data = device_data[primary_ip]
            logging.info(f"Primary device: {primary_ip} with {primary_data['user_count']} users "
                        f"and {primary_data['template_count']} templates")
            
            # Sync from primary to other devices
            sync_results = {}
            total_users_synced = 0
            total_templates_synced = 0
            
            for target_ip, target_data in device_data.items():
                if target_ip == primary_ip:
                    continue
                
                try:
                    result = self.sync_users_and_templates(
                        device_connections[primary_ip], device_connections[target_ip],
                        primary_data, target_data,
                        primary_ip, target_ip
                    )
                    
                    sync_results[target_ip] = result
                    total_users_synced += result['users_synced']
                    total_templates_synced += result['templates_synced']
                    
                    logging.info(f"Synced {result['users_synced']} users and "
                               f"{result['templates_synced']} templates to {target_ip}")
                    
                except Exception as e:
                    logging.error(f"Error syncing to {target_ip}: {e}")
                    sync_results[target_ip] = {'users_synced': 0, 'templates_synced': 0}
            
            total_time = time.time() - start_time
            
            return {
                'success': True,
                'primary_device': primary_ip,
                'total_users_synced': total_users_synced,
                'total_templates_synced': total_templates_synced,
                'sync_time': total_time,
                'device_results': sync_results,
                'device_data': {ip: {
                    'user_count': data['user_count'],
                    'template_count': data['template_count'],
                    'face_capability': data['face_capability']
                } for ip, data in device_data.items()},
                'face_template_note': 'Face templates detected but not synced due to pyzk library limitations'
            }
            
        except Exception as e:
            logging.error(f"Error in device sync: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_users_synced': 0,
                'total_templates_synced': 0
            }
            
        finally:
            # Disconnect all devices
            for ip, conn in device_connections.items():
                try:
                    conn.disconnect()
                    logging.info(f"Disconnected from {ip}")
                except Exception as e:
                    logging.warning(f"Error disconnecting from {ip}: {e}")


def test_working_sync():
    """Test the working sync solution"""
    device_ips = ["192.168.41.212", "192.168.41.205"]
    
    print("Working Sync Solution Test")
    print("=" * 50)
    print(f"Testing devices: {device_ips}")
    print("Note: Face templates will be detected but not synced due to library limitations")
    print()
    
    sync_manager = WorkingSyncSolution()
    result = sync_manager.sync_devices(device_ips, limit_users=100)
    
    print("Sync Results:")
    print("=" * 30)
    print(f"Success: {result['success']}")
    
    if result['success']:
        print(f"Primary Device: {result['primary_device']}")
        print(f"Users Synced: {result['total_users_synced']}")
        print(f"Templates Synced: {result['total_templates_synced']}")
        print(f"Sync Time: {result['sync_time']:.2f} seconds")
        
        print("\nDevice Data:")
        for ip, data in result['device_data'].items():
            face_info = data['face_capability']
            print(f"  {ip}:")
            print(f"    Users: {data['user_count']}")
            print(f"    Fingerprint Templates: {data['template_count']}")
            print(f"    Face Version: {face_info.get('face_version', 'Unknown')}")
            print(f"    Face Function: {'Enabled' if face_info.get('face_function_enabled') else 'Disabled'}")
            print(f"    Reported Face Count: {face_info.get('reported_face_count', 0)}")
        
        print(f"\nNote: {result.get('face_template_note', '')}")
        
    else:
        print(f"Error: {result.get('message', result.get('error', 'Unknown error'))}")


if __name__ == "__main__":
    test_working_sync()