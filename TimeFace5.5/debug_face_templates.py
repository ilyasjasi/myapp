#!/usr/bin/env python3
"""
Debug Face Template Retrieval - Test different methods to get face templates
"""

import logging
import struct
from zk import ZK

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def debug_face_template_methods(ip_address="192.168.41.212"):
    """Debug different methods to retrieve face templates"""
    
    print(f"Debugging Face Template Methods for {ip_address}")
    print("=" * 60)
    
    try:
        # Connect to device
        zk = ZK(ip_address, port=4370, timeout=15, ommit_ping=True)
        conn = zk.connect()
        print(f"✓ Connected to {ip_address}")
        
        # Get device info
        print(f"Device info:")
        try:
            print(f"  Firmware: {getattr(conn, 'firmware_version', 'Unknown')}")
            print(f"  Platform: {getattr(conn, 'platform', 'Unknown')}")
            print(f"  Face count: {getattr(conn, 'faces', 'Unknown')}")
        except Exception as e:
            print(f"  Error getting device info: {e}")
        
        # Get first 5 users for testing
        users = conn.get_users()
        if not users:
            print("No users found on device")
            return
        
        test_users = users[:5]  # Test with first 5 users
        print(f"\nTesting face template retrieval with {len(test_users)} users:")
        
        for i, user in enumerate(test_users):
            print(f"\nUser {i+1}: {user.user_id} (UID: {user.uid}, Name: {user.name})")
            
            # Method 1: Standard get_face_template
            print("  Method 1: Standard get_face_template")
            try:
                if hasattr(conn, 'get_face_template'):
                    result = conn.get_face_template(uid=user.uid)
                    if result:
                        print(f"    ✓ Success: {type(result)} - {len(result) if hasattr(result, '__len__') else 'N/A'} bytes")
                    else:
                        print("    ✗ No result")
                else:
                    print("    ✗ Method not available")
            except Exception as e:
                print(f"    ✗ Error: {e}")
            
            # Method 2: Raw command 1503
            print("  Method 2: Raw command 1503 (GET_FACE_TEMPLATE)")
            try:
                command_data = struct.pack('<I', user.uid)
                result = conn.send_command(1503, command_data)
                if result:
                    print(f"    ✓ Success: {len(result)} bytes")
                    if len(result) >= 4:
                        template_size = struct.unpack('<I', result[:4])[0]
                        print(f"    Template size: {template_size}")
                        if template_size > 0 and len(result) >= 4 + template_size:
                            print(f"    ✓ Valid template data: {template_size} bytes")
                        else:
                            print(f"    ✗ Invalid template data")
                else:
                    print("    ✗ No result")
            except Exception as e:
                print(f"    ✗ Error: {e}")
            
            # Method 3: read_with_buffer commands
            print("  Method 3: read_with_buffer with various commands")
            for cmd in [1503, 1504, 1505]:
                try:
                    result = conn.read_with_buffer(cmd, user.uid)
                    if result:
                        print(f"    ✓ Command {cmd}: {len(result)} bytes")
                    else:
                        print(f"    ✗ Command {cmd}: No result")
                except Exception as e:
                    print(f"    ✗ Command {cmd}: {e}")
            
            # Method 4: Check if user has face data using device attributes
            print("  Method 4: Check user face data indicators")
            try:
                # Check user attributes that might indicate face data
                attrs = ['face', 'face_template', 'has_face']
                for attr in attrs:
                    if hasattr(user, attr):
                        value = getattr(user, attr)
                        print(f"    User.{attr}: {value}")
                
                # Try to get face template using different UIDs/formats
                for uid_variant in [user.uid, user.user_id]:
                    try:
                        if hasattr(conn, 'get_face_template'):
                            result = conn.get_face_template(uid=uid_variant)
                            if result:
                                print(f"    ✓ Face template found using {uid_variant}")
                                break
                    except:
                        continue
                        
            except Exception as e:
                print(f"    ✗ Error checking user attributes: {e}")
        
        # Method 5: Try to get all face templates at once
        print(f"\nMethod 5: Bulk face template retrieval")
        try:
            # Try different bulk methods
            bulk_methods = [
                ('get_face_templates', lambda: getattr(conn, 'get_face_templates', lambda: None)()),
                ('get_faces', lambda: getattr(conn, 'get_faces', lambda: None)()),
                ('read_with_buffer 1503', lambda: conn.read_with_buffer(1503)),
            ]
            
            for method_name, method_func in bulk_methods:
                try:
                    result = method_func()
                    if result:
                        print(f"  ✓ {method_name}: {type(result)} - {len(result) if hasattr(result, '__len__') else 'N/A'}")
                    else:
                        print(f"  ✗ {method_name}: No result")
                except Exception as e:
                    print(f"  ✗ {method_name}: {e}")
                    
        except Exception as e:
            print(f"  ✗ Error in bulk retrieval: {e}")
        
        # Method 6: Check device capabilities
        print(f"\nMethod 6: Device capability analysis")
        try:
            capabilities = []
            
            # Check available methods
            face_methods = ['get_face_template', 'get_face_templates', 'get_faces', 
                          'set_face_template', 'save_face_template']
            
            for method in face_methods:
                if hasattr(conn, method):
                    capabilities.append(method)
            
            print(f"  Available face methods: {capabilities}")
            
            # Check device attributes
            face_attrs = ['faces', 'face_version', 'face_fun_on']
            for attr in face_attrs:
                try:
                    if hasattr(conn, attr):
                        value = getattr(conn, attr)
                        print(f"  Device.{attr}: {value}")
                except Exception as e:
                    print(f"  Device.{attr}: Error - {e}")
                    
        except Exception as e:
            print(f"  ✗ Error checking capabilities: {e}")
        
        conn.disconnect()
        print(f"\n✓ Disconnected from {ip_address}")
        
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    debug_face_template_methods()