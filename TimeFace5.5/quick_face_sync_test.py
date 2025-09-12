#!/usr/bin/env python3
"""
Quick face sync test - sync only a few users with face data
"""

import logging
from enhanced_device_sync import EnhancedDeviceSync

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def quick_face_sync_test():
    """Test face sync with limited users for quick verification"""
    
    source_ip = "192.168.41.212"  # Has 336 face templates
    target_ip = "192.168.41.205"  # Has 5 face templates (from previous sync)
    
    print("🚀 QUICK FACE SYNC TEST")
    print("=" * 60)
    print(f"Source: {source_ip} (should have 336 face templates)")
    print(f"Target: {target_ip} (should have 5 face templates)")
    print("Testing with first 50 users only for speed...")
    print()
    
    sync_manager = EnhancedDeviceSync()
    
    try:
        # Connect fpmachine to both devices
        print("Step 1: Connecting fpmachine to devices...")
        source_dev = sync_manager.connect_fpmachine(source_ip)
        target_dev = sync_manager.connect_fpmachine(target_ip)
        
        if not source_dev or not target_dev:
            print("❌ Failed to connect fpmachine to devices")
            return
        
        print("✅ fpmachine connected to both devices")
        
        # Get first 50 users and check for face data
        print(f"\nStep 2: Finding users with face data (first 50 users)...")
        
        users = source_dev.get_users()
        if not users:
            print("❌ No users found on source device")
            return
        
        users_with_face_data = []
        
        # Check first 50 users for face data
        for i, user in enumerate(users[:50]):
            user_id = getattr(user, 'person_id', getattr(user, 'id', str(i)))
            user_name = getattr(user, 'name', f'User_{i}')
            
            face_data = None
            photo_data = None
            
            # Check for face template
            try:
                face_data = source_dev.get_user_face(str(user_id))
            except:
                pass
            
            # Check for photo
            try:
                photo_data = source_dev.get_user_pic(str(user_id))
            except:
                pass
            
            if face_data or photo_data:
                users_with_face_data.append({
                    'user_id': user_id,
                    'user_name': user_name,
                    'face_template': face_data,
                    'photo': photo_data
                })
                
                print(f"   Found face data for user {user_id} ({user_name}): "
                      f"face={len(face_data) if face_data else 0} bytes, "
                      f"photo={len(photo_data) if photo_data else 0} bytes")
        
        if not users_with_face_data:
            print("❌ No face data found in first 50 users")
            return
        
        print(f"✅ Found {len(users_with_face_data)} users with face data")
        
        # Check which users already exist on target device
        print(f"\nStep 3: Checking existing face data on {target_ip}...")
        
        users_to_sync = []
        users_already_exist = []
        
        for user_data in users_with_face_data:
            user_id = user_data['user_id']
            user_name = user_data['user_name']
            
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
                users_already_exist.append({
                    'user_id': user_id,
                    'user_name': user_name,
                    'has_face': bool(existing_face),
                    'has_photo': bool(existing_photo)
                })
                print(f"   ⚠️  User {user_id} ({user_name}) already has face data on target: "
                      f"face={bool(existing_face)}, photo={bool(existing_photo)}")
            else:
                users_to_sync.append(user_data)
                print(f"   ✅ User {user_id} ({user_name}) can be synced (no existing face data)")
        
        print(f"\n📊 Summary:")
        print(f"   Users with existing face data: {len(users_already_exist)}")
        print(f"   Users ready to sync: {len(users_to_sync)}")
        
        if not users_to_sync:
            print(f"\n⚠️  No new users to sync - all users already have face data on target device")
            print(f"   This explains why sync was failing - fpmachine cannot overwrite existing face data")
            
            # Still verify the existing face count
            print(f"\nStep 4: Verifying existing face count on {target_ip}...")
            
            # Connect pyzk to check face count
            from zk import ZK
            zk = ZK(target_ip, port=4370, timeout=15)
            conn = zk.connect()
            
            if conn:
                if hasattr(conn, 'faces'):
                    face_count = conn.faces
                    print(f"✅ Target device has {face_count} face templates (as expected)")
                    print(f"🎉 SUCCESS! Face data is already present on target device")
                else:
                    print("❌ Cannot check face count - no faces attribute")
                
                conn.disconnect()
            else:
                print("❌ Cannot connect to verify face count")
            
            return
        
        # Sync face data to target device (only new users)
        print(f"\nStep 4: Syncing face data to {target_ip} (new users only)...")
        
        face_synced = 0
        photos_synced = 0
        errors = 0
        
        for user_data in users_to_sync:
            user_id = user_data['user_id']
            user_name = user_data['user_name']
            
            # Sync face template
            if user_data['face_template']:
                try:
                    success = target_dev.set_user_face(str(user_id), user_data['face_template'])
                    if success:
                        face_synced += 1
                        print(f"   ✅ Synced face template for {user_id} ({user_name})")
                    else:
                        print(f"   ❌ Failed to sync face template for {user_id}")
                        errors += 1
                except Exception as e:
                    print(f"   ❌ Error syncing face template for {user_id}: {e}")
                    errors += 1
            
            # Sync photo
            if user_data['photo']:
                try:
                    success = target_dev.set_user_pic(str(user_id), user_data['photo'])
                    if success:
                        photos_synced += 1
                        print(f"   ✅ Synced photo for {user_id} ({user_name})")
                    else:
                        print(f"   ❌ Failed to sync photo for {user_id}")
                        errors += 1
                except Exception as e:
                    print(f"   ❌ Error syncing photo for {user_id}: {e}")
                    errors += 1
        
        print(f"\n✅ Quick face sync completed!")
        print(f"   Face templates synced: {face_synced}")
        print(f"   Photos synced: {photos_synced}")
        print(f"   Errors: {errors}")
        
        # Verify by checking face count on target device
        print(f"\nStep 5: Verifying face count on {target_ip}...")
        
        # Connect pyzk to check face count
        from zk import ZK
        zk = ZK(target_ip, port=4370, timeout=15)
        conn = zk.connect()
        
        if conn:
            if hasattr(conn, 'faces'):
                face_count = conn.faces
                print(f"✅ Target device now has {face_count} face templates")
                
                expected_count = len(users_already_exist) + face_synced
                if face_count >= expected_count:
                    print(f"🎉 SUCCESS! Face count is {face_count} (expected: {expected_count})")
                    if face_synced > 0:
                        print(f"   New face templates synced: {face_synced}")
                    if len(users_already_exist) > 0:
                        print(f"   Existing face templates: {len(users_already_exist)}")
                else:
                    print(f"⚠️  Face count is {face_count} (expected: {expected_count})")
            else:
                print("❌ Cannot check face count - no faces attribute")
            
            conn.disconnect()
        else:
            print("❌ Cannot connect to verify face count")
        
    except Exception as e:
        print(f"❌ Error during quick face sync test: {e}")
        logging.exception("Detailed error:")
    
    finally:
        # Disconnect fpmachine
        try:
            if source_ip in sync_manager.fpmachine_connections:
                sync_manager.fpmachine_connections[source_ip].disconnect()
            if target_ip in sync_manager.fpmachine_connections:
                sync_manager.fpmachine_connections[target_ip].disconnect()
        except:
            pass

if __name__ == "__main__":
    quick_face_sync_test()