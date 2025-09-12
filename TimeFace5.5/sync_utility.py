#!/usr/bin/env python3
"""
Device Sync Utility
Easy-to-use utility for syncing ZKTeco devices
"""

import logging
import sys
from enhanced_device_sync import EnhancedDeviceSync, update_devices, sync_devices_in_area

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('device_sync.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

def sync_by_ip_addresses():
    """Sync devices by providing IP addresses directly"""
    print("Sync Devices by IP Addresses")
    print("-" * 40)
    
    ip_input = input("Enter device IP addresses (comma-separated): ")
    if not ip_input.strip():
        print("No IP addresses provided.")
        return
    
    ip_addresses = [ip.strip() for ip in ip_input.split(',')]
    print(f"Syncing devices: {ip_addresses}")
    
    try:
        result = update_devices(ip_addresses)
        print(f"\nSync completed: {result}")
    except Exception as e:
        print(f"Error during sync: {e}")
        logging.error(f"Sync error: {e}")

def sync_by_area():
    """Sync devices by area ID"""
    print("Sync Devices by Area")
    print("-" * 40)
    
    try:
        area_id = int(input("Enter area ID: "))
    except ValueError:
        print("Invalid area ID. Please enter a number.")
        return
    
    print(f"Syncing devices in area {area_id}...")
    
    try:
        result = sync_devices_in_area(area_id)
        print(f"\nArea sync completed:")
        print(f"  Success: {result.get('success', False)}")
        print(f"  Synced devices: {result.get('synced_devices', 0)}")
        print(f"  Users synced: {result.get('total_users_synced', 0)}")
        print(f"  Templates synced: {result.get('total_templates_synced', 0)}")
        if 'primary_device' in result:
            print(f"  Primary device: {result['primary_device']}")
        if 'error' in result:
            print(f"  Error: {result['error']}")
    except Exception as e:
        print(f"Error during area sync: {e}")
        logging.error(f"Area sync error: {e}")

def main():
    """Main menu"""
    while True:
        print("\n" + "=" * 50)
        print("Enhanced Device Sync Utility")
        print("=" * 50)
        print("1. Sync devices by IP addresses")
        print("2. Sync devices by area ID")
        print("3. Exit")
        print("-" * 50)
        
        choice = input("Select an option (1-3): ").strip()
        
        if choice == '1':
            sync_by_ip_addresses()
        elif choice == '2':
            sync_by_area()
        elif choice == '3':
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please select 1, 2, or 3.")

if __name__ == "__main__":
    main()