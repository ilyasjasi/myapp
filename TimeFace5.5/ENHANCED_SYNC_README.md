# Enhanced Device Sync for ZKTeco Devices

## Overview

The Enhanced Device Sync module provides comprehensive synchronization of users, fingerprint templates, and face templates between ZKTeco devices. It addresses your requirements for:

- **Primary Device Detection**: Automatically identifies the device with the most users and templates as the primary source
- **Comprehensive Sync**: Syncs both users and all types of templates (fingerprint and face)
- **Bidirectional Sync**: Ensures all devices have the same users and templates
- **Face Template Support**: Attempts to handle face templates using various methods
- **Area-based Sync**: Syncs all devices within a specific area

## Key Features

### 1. Smart Primary Device Selection
- Automatically selects the device with the most users + templates as the primary source
- Example: Device A (100 users, 80 templates) becomes primary over Device B (20 users, 15 templates)

### 2. Template Type Support
- **Fingerprint Templates**: Full support using `get_user_template()` and `save_user_template()`
- **Face Templates**: Attempts multiple methods to retrieve and save face templates:
  - Checks for `get_face_template()` method
  - Uses `read_with_buffer()` with face template commands (1503, 1504, 1505)
  - Attempts raw command sending for face data

### 3. Comprehensive Sync Process
1. **Connect** to all devices in the area
2. **Collect** user and template data from each device
3. **Identify** primary device (most users + templates)
4. **Sync** from primary to all other devices
5. **Bidirectional sync** from other devices back to primary
6. **Ensure** all devices have identical users and templates

## Usage

### Method 1: Using the Utility Script
```bash
python sync_utility.py
```
This provides an interactive menu to:
- Sync devices by IP addresses
- Sync devices by area ID

### Method 2: Direct Function Calls

#### Sync by IP Addresses
```python
from enhanced_device_sync import update_devices

# List of device IP addresses
device_ips = ["192.168.1.100", "192.168.1.101", "192.168.1.102"]
result = update_devices(device_ips)
print(result)
```

#### Sync by Area ID
```python
from enhanced_device_sync import sync_devices_in_area

# Sync all devices in area 1
result = sync_devices_in_area(area_id=1)
print(result)
```

### Method 3: Integration with Device Manager
The enhanced sync is automatically integrated into your existing `DeviceManager` class:

```python
from device_manager import DeviceManager

dm = DeviceManager()
result = dm.sync_devices_in_area(area_id=1)
```

## Configuration

### Database Requirements
The sync module expects a SQLite database at `instance/attendance.db` with a `devices` table containing:
- `device_id`: Unique device identifier
- `ip_address`: Device IP address
- `area_id`: Area identifier for grouping devices
- `online_status`: 1 for online, 0 for offline

### ZK Library Requirements
Ensure the `pyzk` library is installed:
```bash
pip install pyzk
```

## Face Template Handling

The module attempts to handle face templates using multiple approaches:

### 1. Standard Methods
- Checks if device supports `get_face_version()`
- Attempts to use `get_face_template()` if available

### 2. Raw Command Methods
- Uses `read_with_buffer()` with commands 1503, 1504, 1505
- Attempts direct command sending for face data

### 3. Fallback Behavior
- If face templates are not supported, continues with fingerprint templates only
- Logs warnings for unsupported face template operations

## Return Values

### Success Response
```python
{
    'success': True,
    'synced_devices': 3,
    'total_users_synced': 25,
    'total_templates_synced': 45,
    'primary_device': '192.168.1.100'
}
```

### Error Response
```python
{
    'success': False,
    'error': 'Error message',
    'synced_devices': 0,
    'total_users_synced': 0,
    'total_templates_synced': 0
}
```

## Logging

The module provides comprehensive logging:
- **INFO**: General sync progress and results
- **WARNING**: Non-critical issues (e.g., face templates not supported)
- **ERROR**: Critical errors that prevent sync

Logs are written to both console and `device_sync.log` file.

## Example Scenarios

### Scenario 1: Empty Device Sync
- Device A: 100 users, 80 templates (becomes primary)
- Device B: Empty
- Device C: 20 users, 15 templates

**Result**: Device B gets all 100 users and 80 templates from Device A, plus 20 users and 15 templates from Device C.

### Scenario 2: Partial Sync
- Device A: Users 1-50 with templates (becomes primary)
- Device B: Users 51-100 with templates
- Device C: Users 1-25 with templates

**Result**: All devices end up with users 1-100 and all available templates.

## Troubleshooting

### Common Issues

1. **Connection Failures**
   - Check device IP addresses and network connectivity
   - Ensure devices are powered on and accessible
   - Verify firewall settings

2. **Face Template Errors**
   - Face templates may not be supported on all device models
   - Check device firmware version and capabilities
   - Review logs for specific error messages

3. **UID Conflicts**
   - The module automatically handles UID assignment
   - Uses incremental UID assignment to avoid conflicts

4. **Database Connection Issues**
   - Ensure `instance/attendance.db` exists and is accessible
   - Check database schema matches expected structure

### Debug Mode
Enable debug logging for detailed information:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Performance Considerations

- **Batch Processing**: Processes users in batches to prevent timeouts
- **Connection Management**: Properly manages device connections and disconnections
- **Memory Usage**: Efficiently handles large numbers of users and templates
- **Timeout Handling**: Includes timeout mechanisms to prevent hanging

## Compatibility

- **ZKTeco Devices**: Compatible with most ZKTeco attendance devices
- **Template Types**: Supports fingerprint templates, attempts face template support
- **Python Version**: Requires Python 3.6+
- **Dependencies**: pyzk library, sqlite3 (built-in)

## Support

For issues or questions:
1. Check the logs for detailed error information
2. Verify device connectivity and capabilities
3. Test with a small number of devices first
4. Review the ZKTeco device documentation for specific model capabilities