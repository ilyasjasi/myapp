#!/usr/bin/env python3
"""
Comprehensive Device Sync Module
Handles syncing users, fingerprint templates, and face templates between ZKTeco devices
"""

import logging
import time
from typing import Dict, List, Tuple, Optional, Any
import sqlite3
import os

class ComprehensiveDeviceSync:
    """Comprehensive sync for ZKTeco devices supporting fingerprint and face templates"""
    
    def __init__(self, device_manager):
        self.device_manager = device_manager
        self.sync_queue = set()
        
    def get_all_templates_from_device(self, conn, users) -> Dict[str, Dict[str, Any]]:
        """Get all templates (fingerprint and face) from a device"""
        templates = {}
        
        for user in users:
            user_templates = {'fingerprint': None, 'face': None}
            
            try:
                # Get fingerprint templates
                fingerprint_template = conn.get_user_template(uid=user.uid)
                if fingerprint_template:
                    user_templates['fingerprint'] = fingerprint_template
                    
            except Exception as e:
                logging.warning(f"Error getting fingerprint template for user {user.user_id}: {e}")
            
            try:
                # Try to get face template using different methods
                # Method 1: Check if device has face template methods
                if hasattr(conn, 'get_face_template'):
                    face_template = conn.get_face_template(uid=user.uid)
                    if face_template:
                        user_templates['face'] = face_template
                        
                # Method 2: Try using raw command for face templates
                elif hasattr(conn, 'send_command'):
                    # ZKTeco face template command (this is device-specific)
                    try:
                        # CMD_GET_FACE_TEMPLATE = 1503 (example command)
                        face_data = conn.send_command(1503, f"{user.uid}".encode())
                        if face_data:
                            user_templates['face'] = face_data
                    except:
                        pass
                        
            except Exception as e:
                logging.warning(f"Error getting face template for user {user.user_id}: {e}")
            
            # Only add if user has at least one template
            if user_templates['fingerprint'] or user_templates['face']:
                templates[user.user_id] = user_templates
                
        return templates
    
    def save_templates_to_device(self, conn, user_uid: int, templates: Dict[str, Any]) -> bool:
        """Save templates (fingerprint and face) to a device"""
        success = False
        
        try:
            # Save fingerprint template
            if templates.get('fingerprint'):
                conn.save_user_template(user=user_uid, fingers=templates['fingerprint'])
                success = True
                logging.info(f"Saved fingerprint template for UID {user_uid}")
                
        except Exception as e:
            logging.warning(f"Error saving fingerprint template for UID {user_uid}: {e}")
        
        try:
            # Save face template
            if templates.get('face'):
                # Method 1: Check if device has face template methods
                if hasattr(conn, 'save_face_template'):
                    conn.save_face_template(uid=user_uid, template=templates['face'])
                    success = True
                    logging.info(f"Saved face template for UID {user_uid}")
                    
                # Method 2: Try using raw command for face templates
                elif hasattr(conn, 'send_command'):
                    try:
                        # CMD_SET_FACE_TEMPLATE = 1504 (example command)
                        conn.send_command(1504, f"{user_uid}:{templates['face']}".encode())
                        success = True
                        logging.info(f"Saved face template for UID {user_uid}")
                    except:
                        pass
                        
        except Exception as e:
            logging.warning(f"Error saving face template for UID {user_uid}: {e}")
            
        return success
    
    def sync_devices_in_area(self, area_id: int) -> Dict[str, Any]:
        """Comprehensive sync of all devices in an area - users and all templates"""
        try:
            # Check if sync is already in progress
            sync_key = f"comprehensive_sync_{area_id}"
            if sync_key in self.sync_queue:
                logging.info(f"Comprehensive sync already in progress for area {area_id}")
                return {
                    'success': False,
                    'message': 'Sync already in progress',
                    'synced_devices': 0,
                    'total_users_synced': 0,
                    'total_templates_synced': 0
                }
            
            self.sync_queue.add(sync_key)
            
            try:
                # Get all online devices in the area
                conn = sqlite3.connect('instance/attendance.db')
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT device_id, ip_address FROM devices 
                    WHERE area_id = ? AND online_status = 1
                """, (area_id,))
                devices = cursor.fetchall()
                conn.close()
                
                if len(devices) < 2:
                    return {
                        'success': True,
                        'message': 'Less than 2 devices in area',
                        'synced_devices': 0,
                        'total_users_synced': 0,
                        'total_templates_synced': 0,
                        'primary_device': None
                    }
                
                logging.info(f"Starting comprehensive sync for {len(devices)} devices in area {area_id}")
                
                # Step 1: Connect to all devices and collect data
                device_connections = {}
                device_data = {}
                
                for device_id, ip_address in devices:
                    try:
                        device_conn = self.device_manager.connect_device(ip_address)
                        if device_conn:
                            device_connections[ip_address] = device_conn
                            
                            # Get users
                            users = device_conn.get_users() or []
                            
                            # Get all templates (fingerprint and face)
                            templates = self.get_all_templates_from_device(device_conn, users)
                            
                            device_data[ip_address] = {
                                'device_id': device_id,
                                'users': {user.user_id: user for user in users},
                                'templates': templates,
                                'user_count': len(users),
                                'template_count': len(templates)
                            }
                            
                            logging.info(f"Device {ip_address}: {len(users)} users, {len(templates)} templates")
                            
                    except Exception as e:
                        logging.error(f"Error connecting to device {ip_address}: {e}")
                        continue
                
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
                logging.info(f"Primary device: {primary_ip} with {primary_data['user_count']} users and {primary_data['template_count']} templates")
                
                # Step 3: Sync from primary to all other devices
                synced_devices = 0
                total_users_synced = 0
                total_templates_synced = 0
                
                primary_conn = device_connections[primary_ip]
                primary_users = primary_data['users']
                primary_templates = primary_data['templates']
                
                for target_ip, target_data in device_data.items():
                    if target_ip == primary_ip:
                        continue
                    
                    try:
                        target_conn = device_connections[target_ip]
                        target_users = target_data['users']
                        target_templates = target_data['templates']
                        
                        logging.info(f"Syncing from primary {primary_ip} to {target_ip}")
                        
                        # Find max UID on target device
                        existing_uids = {user.uid for user in target_users.values()}
                        max_uid = max(existing_uids) if existing_uids else 0
                        
                        users_added = 0
                        templates_added = 0
                        
                        # Add missing users from primary to target
                        for user_id, user in primary_users.items():
                            if user_id not in target_users:
                                try:
                                    new_uid = max_uid + 1
                                    max_uid += 1
                                    
                                    # Add user
                                    target_conn.set_user(
                                        uid=new_uid,
                                        name=user.name,
                                        privilege=user.privilege,
                                        password=user.password,
                                        group_id=getattr(user, 'group_id', ''),
                                        user_id=user.user_id
                                    )
                                    users_added += 1
                                    
                                    # Add templates if available
                                    if user_id in primary_templates:
                                        if self.save_templates_to_device(target_conn, new_uid, primary_templates[user_id]):
                                            templates_added += 1
                                    
                                    logging.info(f"Added user {user_id} with templates to {target_ip}")
                                    
                                except Exception as e:
                                    logging.error(f"Failed to add user {user_id} to {target_ip}: {e}")
                        
                        # Add missing templates for existing users
                        for user_id, template_data in primary_templates.items():
                            if user_id in target_users and user_id not in target_templates:
                                try:
                                    target_user_uid = target_users[user_id].uid
                                    if self.save_templates_to_device(target_conn, target_user_uid, template_data):
                                        templates_added += 1
                                        logging.info(f"Added templates for existing user {user_id} on {target_ip}")
                                except Exception as e:
                                    logging.warning(f"Failed to add templates for existing user {user_id}: {e}")
                        
                        # Step 4: Bidirectional sync - sync back from target to primary
                        for user_id, user in target_users.items():
                            if user_id not in primary_users:
                                try:
                                    primary_max_uid = max([u.uid for u in primary_users.values()]) if primary_users else 0
                                    primary_max_uid += 1
                                    
                                    # Add user to primary
                                    primary_conn.set_user(
                                        uid=primary_max_uid,
                                        name=user.name,
                                        privilege=user.privilege,
                                        password=user.password,
                                        group_id=getattr(user, 'group_id', ''),
                                        user_id=user.user_id
                                    )
                                    users_added += 1
                                    
                                    # Add templates if available
                                    if user_id in target_templates:
                                        if self.save_templates_to_device(primary_conn, primary_max_uid, target_templates[user_id]):
                                            templates_added += 1
                                    
                                    logging.info(f"Added user {user_id} from {target_ip} to primary {primary_ip}")
                                    
                                except Exception as e:
                                    logging.error(f"Failed to add user {user_id} to primary: {e}")
                        
                        total_users_synced += users_added
                        total_templates_synced += templates_added
                        synced_devices += 1
                        
                        logging.info(f"Completed sync to {target_ip}: {users_added} users, {templates_added} templates")
                        
                    except Exception as e:
                        logging.error(f"Error syncing to device {target_ip}: {e}")
                        continue
                
                return {
                    'success': True,
                    'synced_devices': synced_devices,
                    'total_users_synced': total_users_synced,
                    'total_templates_synced': total_templates_synced,
                    'primary_device': primary_ip
                }
                
            finally:
                # Disconnect all devices
                for ip, conn in device_connections.items():
                    try:
                        self.device_manager.disconnect_device(conn)
                    except Exception as e:
                        logging.warning(f"Error disconnecting from {ip}: {e}")
                
                # Remove from sync queue
                self.sync_queue.discard(sync_key)
                
        except Exception as e:
            logging.error(f"Error in comprehensive area sync: {e}")
            return {
                'success': False,
                'error': str(e),
                'synced_devices': 0,
                'total_users_synced': 0,
                'total_templates_synced': 0
            }