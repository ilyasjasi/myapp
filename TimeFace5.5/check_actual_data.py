#!/usr/bin/env python3
"""
Check actual data counts by fetching data from devices
"""

import logging
from zk import ZK

# Configure logging
logging.basicConfig(level=logging.INFO)

def check_actual_data(ip_address: str):
    """Check actual data by fetching it"""
    
    print(f"\nChecking actual data for: {ip_address}")
    print("-" * 50)
    
    try:
        # Connect with pyzk
        zk = ZK(ip_address, port=4370, timeout=60)
        conn = zk.connect()
        
        if conn:
            print("✅ pyzk connection successful")
            
            # Check attributes before fetching data
            print(f"Before data fetch - faces: {conn.faces}, users: {conn.users}")
            
            # Fetch users
            try:
                users = conn.get_users()
                print(f"✅ Users fetched: {len(users)} users")
                print(f"After user fetch - users: {conn.users}")
            except Exception as e:
                print(f"❌ Users fetch failed: {e}")
            
            # Fetch fingerprint templates
            try:
                templates = conn.get_templates()
                print(f"✅ Fingerprint templates fetched: {len(templates)} templates")
            except Exception as e:
                print(f"❌ Fingerprint templates fetch failed: {e}")
            
            # Check faces attribute after user fetch
            print(f"After fetches - faces: {conn.faces}, users: {conn.users}")
            
            # Try to get face templates (this might fail due to send_command issue)
            try:
                face_templates = conn.get_face_templates()
                if face_templates:
                    print(f"✅ Face templates fetched: {len(face_templates)} face templates")
                else:
                    print(f"⚠️ Face templates: None returned")
            except Exception as e:
                print(f"❌ Face templates fetch failed: {e}")
            
            # Final attribute check
            print(f"Final - faces: {conn.faces}, users: {conn.users}")
            
            conn.disconnect()
        else:
            print("❌ pyzk connection failed")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Check actual data for our test devices"""
    
    test_devices = [
        "192.168.41.212",  # Device with face templates
        "192.168.41.205"   # Another device
    ]
    
    print("=" * 60)
    print("ACTUAL DATA CHECKER")
    print("=" * 60)
    print("Checking actual data counts by fetching data...")
    
    for device_ip in test_devices:
        check_actual_data(device_ip)
    
    print(f"\n{'='*60}")
    print("ANALYSIS COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()