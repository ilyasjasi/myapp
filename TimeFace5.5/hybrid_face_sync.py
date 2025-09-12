#!/usr/bin/env python3
"""
Hybrid Face & Photo Sync Solution
Combines pyzk (for users/fingerprints) and fpmachine (for faces/photos)
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from zk import ZK

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('hybrid_sync.log'),
        logging.StreamHandler()
    ]
)

class HybridFaceSync:
    """Hybrid sync solution using both pyzk and fpmachine libraries"""
    
    def __init__(self):
        self.pyzk_connections = {}
        self.fpmachine_connections = {}
        self.device_capabilities = {}
    
    def detect_device_capabilities(self, ip_address: str) -> Dict[str, Any]:
        """Detect what each device supports"""
        capabilities = {
            'pyzk_compatible': False,
            'fpmachine_compatible': False,
            'face_support': False,
            'photo_support': False,
            'device_model': 'Unknown',
            'face_version': 0,
            'user_count': 0
        }
        
        # Test pyzk compatibility
        try:
            zk = ZK(ip_address, port=4370, timeout=15, ommit_ping=True)
            conn = zk.connect()
            if conn:
                capabilities['pyzk_compatible'] = True
                
                # Get basic info
                users = conn.get_users() or []
                capabilities['user_count'] = len(users)
                
                # Check face support
                if hasattr(conn, 'get_face_version'):
                    capabilities['face_version'] = conn.get_face_version()
                    capabilities['face_support'] = capabilities['face_version'] > 0
                
                conn.disconnect()
                logging.info(f"pyzk: {ip_address} compatible, {len(users)} users, face version {capabilities['face_version']}")
        except Exception as e:
            logging.debug(f"pyzk: {ip_address} not compatible: {e}")
        
        # Test fpmachine compatibility
        try:
            from fpmachine.devices import ZMM220_TFT, ZMM100_TFT
            
            for device_name, device_class in [("ZMM220_TFT", ZMM220_TFT), ("ZMM100_TFT", ZMM100_TFT)]:
                try:
                    dev = device_class(ip_address, 4370, "latin-1")
                    if dev.connect(0):
                        capabilities['fpmachine_compatible'] = True
                        capabilities['device_model'] = device_name
                        
                        # Check face and photo support
                        if hasattr(dev, 'face_fun_on'):
                            capabilities['face_support'] = bool(dev.face_fun_on)
                        if hasattr(dev, 'zk_face_version'):
                            capabilities['face_version'] = dev.zk_face_version
                        
                        # Test if we can actually get face/photo data
                        try:
                            users = dev.get_users()
                            if users and len(users) > 0:
                                # Test with first user
                                test_user = users[0]
                                user_id = getattr(test_user, 'person_id', getattr(test_user, 'id', '1'))
                                
                                # Test face template
                                try:
                                    face_data = dev.get_user_face(str(user_id))
                                    capabilities['photo_support'] = face_data is not None
                                except:
                                    pass
                                
                                # Test photo
                                try:
                                    photo_data = dev.get_user_pic(str(user_id))
                                    capabilities['photo_support'] = photo_data is not None
                                except:
                                    pass
                        except:
                            pass
                        
                        dev.disconnect()
                        logging.info(f"fpmachine: {ip_address} compatible with {device_name}")
                        break
                except Exception as e:
                    logging.debug(f"fpmachine: {ip_address} not compatible with {device_name}: {e}")
                    
        except ImportError:
            logging.debug(f"fpmachine library not available")
        except Exception as e:
            logging.debug(f"fpmachine: {ip_address} error: {e}")
        
        return capabilities
    
    def connect_pyzk(self, ip_address: str) -> Optional[Any]:
        """Connect using pyzk library"""
        try:
            zk = ZK(ip_address, port=4370, timeout=15, ommit_ping=True)
            conn = zk.connect()
            if conn:
                self.pyzk_connections[ip_address] = conn
                return conn
        except Exception as e:
            logging.error(f"pyzk connection failed for {ip_address}: {e}")
        return None
    
    def connect_fpmachine(self, ip_address: str, device_model: str = "ZMM220_TFT") -> Optional[Any]:
        """Connect using fpmachine library"""
        try:
            from fpmachine.devices import ZMM220_TFT, ZMM100_TFT
            
            device_classes = {
                "ZMM220_TFT": ZMM220_TFT,
                "ZMM100_TFT": ZMM100_TFT
            }
            
            device_class = device_classes.get(device_model, ZMM220_TFT)
            dev = device_class(ip_address, 4370, "latin-1")
            
            if dev.connect(0):
                self.fpmachine_connections[ip_address] = dev
                return dev
        except Exception as e:
            logging.error(f"fpmachine connection failed for {ip_address}: {e}")
        return None
    
    def get_users_with_face_data(self, ip_address: str) -> Dict[str, Dict[str, Any]]:
        """Get users who have face templates or photos"""
        users_with_face_data = {}
        
        if ip_address not in self.fpmachine_connections:
            return users_with_face_data
        
        dev = self.fpmachine_connections[ip_address]
        
        try:
            users = dev.get_users()
            if not users:
                return users_with_face_data
            
            logging.info(f"Checking {len(users)} users for face/photo data on {ip_address}")
            
            for i, user in enumerate(users):
                if i % 50 == 0:  # Progress every 50 users
                    logging.info(f"  Progress: {i}/{len(users)} users checked")
                
                user_id = getattr(user, 'person_id', getattr(user, 'id', str(i)))
                user_data = {
                    'user_object': user,
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
                        logging.debug(f"Found face template for user {user_id}: {len(face_data)} bytes")
                except Exception as e:
                    logging.debug(f"No face template for user {user_id}: {e}")
                
                # Check for photo
                try:
                    photo_data = dev.get_user_pic(str(user_id))
                    if photo_data and len(photo_data) > 0:
                        user_data['photo'] = photo_data
                        user_data['has_face_data'] = True
                        logging.debug(f"Found photo for user {user_id}: {len(photo_data)} bytes")
                except Exception as e:
                    logging.debug(f"No photo for user {user_id}: {e}")
                
                if user_data['has_face_data']:
                    users_with_face_data[user_id] = user_data
            
            logging.info(f"Found {len(users_with_face_data)} users with face/photo data on {ip_address}")
            
        except Exception as e:
            logging.error(f"Error getting face data from {ip_address}: {e}")
        
        return users_with_face_data
    
    def sync_face_data(self, source_ip: str, target_ip: str, user_mapping: Dict[str, str]) -> Dict[str, int]:
        """Sync face templates and photos between devices"""
        
        results = {
            'face_templates_synced': 0,
            'photos_synced': 0,
            'errors': 0
        }
        
        if source_ip not in self.fpmachine_connections or target_ip not in self.fpmachine_connections:
            logging.error("Both devices must be connected via fpmachine for face sync")
            return results
        
        source_dev = self.fpmachine_connections[source_ip]
        target_dev = self.fpmachine_connections[target_ip]
        
        # Get users with face data from source
        source_face_data = self.get_users_with_face_data(source_ip)
        
        if not source_face_data:
            logging.info(f"No face data found on source device {source_ip}")
            return results
        
        logging.info(f"Syncing face data from {source_ip} to {target_ip}")
        
        for source_user_id, face_data in source_face_data.items():
            # Find corresponding user on target device
            target_user_id = user_mapping.get(source_user_id, source_user_id)
            
            try:
                # Sync face template
                if face_data['face_template']:
                    try:
                        success = target_dev.set_user_face(target_user_id, face_data['face_template'])
                        if success:
                            results['face_templates_synced'] += 1
                            logging.info(f"✓ Synced face template for user {source_user_id} -> {target_user_id}")
                        else:
                            logging.warning(f"✗ Failed to sync face template for user {source_user_id}")
                            results['errors'] += 1
                    except Exception as e:
                        logging.error(f"Error syncing face template for user {source_user_id}: {e}")
                        results['errors'] += 1
                
                # Sync photo
                if face_data['photo']:
                    try:
                        success = target_dev.set_user_pic(target_user_id, face_data['photo'])
                        if success:
                            results['photos_synced'] += 1
                            logging.info(f"✓ Synced photo for user {source_user_id} -> {target_user_id}")
                        else:
                            logging.warning(f"✗ Failed to sync photo for user {source_user_id}")
                            results['errors'] += 1
                    except Exception as e:
                        logging.error(f"Error syncing photo for user {source_user_id}: {e}")
                        results['errors'] += 1
                        
            except Exception as e:
                logging.error(f"Error syncing data for user {source_user_id}: {e}")
                results['errors'] += 1
        
        return results
    
    def hybrid_sync(self, device_ips: List[str]) -> Dict[str, Any]:
        """Perform complete hybrid sync"""
        
        logging.info(f"Starting hybrid sync with {len(device_ips)} devices")
        start_time = time.time()
        
        # Step 1: Detect capabilities
        logging.info("Step 1: Detecting device capabilities...")
        for ip in device_ips:
            capabilities = self.detect_device_capabilities(ip)
            self.device_capabilities[ip] = capabilities
            logging.info(f"{ip}: pyzk={capabilities['pyzk_compatible']}, "
                        f"fpmachine={capabilities['fpmachine_compatible']}, "
                        f"face_support={capabilities['face_support']}")
        
        # Step 2: Connect to devices
        logging.info("Step 2: Connecting to devices...")
        for ip in device_ips:
            caps = self.device_capabilities[ip]
            
            # Connect via pyzk for users/fingerprints
            if caps['pyzk_compatible']:
                self.connect_pyzk(ip)
            
            # Connect via fpmachine for faces/photos
            if caps['fpmachine_compatible']:
                self.connect_fpmachine(ip, caps['device_model'])
        
        # Step 3: Sync users and fingerprints using pyzk (existing working solution)
        logging.info("Step 3: Syncing users and fingerprints...")
        from working_sync_solution import WorkingSyncSolution
        
        working_sync = WorkingSyncSolution()
        pyzk_result = working_sync.sync_devices(device_ips, limit_users=None)  # Full sync
        
        # Step 4: Sync face templates and photos using fpmachine
        logging.info("Step 4: Syncing face templates and photos...")
        
        # Find primary device (most users)
        primary_ip = max(device_ips, key=lambda ip: self.device_capabilities[ip]['user_count'])
        
        face_sync_results = {}
        total_face_synced = 0
        total_photos_synced = 0
        
        # Create user mapping (assuming user IDs are the same across devices)
        user_mapping = {}  # In real scenario, you might need to map users by name or other attributes
        
        for target_ip in device_ips:
            if target_ip != primary_ip and target_ip in self.fpmachine_connections:
                result = self.sync_face_data(primary_ip, target_ip, user_mapping)
                face_sync_results[target_ip] = result
                total_face_synced += result['face_templates_synced']
                total_photos_synced += result['photos_synced']
        
        # Step 5: Cleanup
        self.disconnect_all()
        
        total_time = time.time() - start_time
        
        return {
            'success': True,
            'total_time': total_time,
            'pyzk_sync': pyzk_result,
            'face_sync_results': face_sync_results,
            'total_face_templates_synced': total_face_synced,
            'total_photos_synced': total_photos_synced,
            'device_capabilities': self.device_capabilities
        }
    
    def disconnect_all(self):
        """Disconnect from all devices"""
        # Disconnect pyzk connections
        for ip, conn in self.pyzk_connections.items():
            try:
                conn.disconnect()
                logging.info(f"Disconnected pyzk from {ip}")
            except Exception as e:
                logging.warning(f"Error disconnecting pyzk from {ip}: {e}")
        
        # Disconnect fpmachine connections
        for ip, dev in self.fpmachine_connections.items():
            try:
                dev.disconnect()
                logging.info(f"Disconnected fpmachine from {ip}")
            except Exception as e:
                logging.warning(f"Error disconnecting fpmachine from {ip}: {e}")
        
        self.pyzk_connections.clear()
        self.fpmachine_connections.clear()


def test_hybrid_sync():
    """Test the hybrid sync solution"""
    device_ips = ["192.168.41.212", "192.168.41.205"]
    
    print("Hybrid Face & Photo Sync Test")
    print("=" * 50)
    print("This solution combines:")
    print("  - pyzk: for users and fingerprint templates")
    print("  - fpmachine: for face templates and photos")
    print()
    
    hybrid_sync = HybridFaceSync()
    
    try:
        result = hybrid_sync.hybrid_sync(device_ips)
        
        print("Hybrid Sync Results:")
        print("=" * 30)
        print(f"Success: {result['success']}")
        print(f"Total Time: {result['total_time']:.2f} seconds")
        
        # Show pyzk results
        pyzk_result = result['pyzk_sync']
        if pyzk_result['success']:
            print(f"\nUsers & Fingerprints (pyzk):")
            print(f"  Users Synced: {pyzk_result['total_users_synced']}")
            print(f"  Templates Synced: {pyzk_result['total_templates_synced']}")
        
        # Show face sync results
        print(f"\nFace & Photos (fpmachine):")
        print(f"  Face Templates Synced: {result['total_face_templates_synced']}")
        print(f"  Photos Synced: {result['total_photos_synced']}")
        
        # Show device capabilities
        print(f"\nDevice Capabilities:")
        for ip, caps in result['device_capabilities'].items():
            print(f"  {ip}:")
            print(f"    Model: {caps['device_model']}")
            print(f"    Users: {caps['user_count']}")
            print(f"    pyzk: {caps['pyzk_compatible']}")
            print(f"    fpmachine: {caps['fpmachine_compatible']}")
            print(f"    Face Support: {caps['face_support']}")
            print(f"    Face Version: {caps['face_version']}")
        
    except Exception as e:
        print(f"Error in hybrid sync: {e}")
        logging.exception("Detailed error:")


if __name__ == "__main__":
    test_hybrid_sync()