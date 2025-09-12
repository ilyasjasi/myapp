from flask_socketio import emit, join_room, leave_room
from flask_login import login_required, current_user
from app import socketio, db
from models import Device
from device_manager import DeviceManager
import threading
import time
import logging

device_manager = DeviceManager()

@socketio.on('connect')
@login_required
def handle_connect():
    """Handle client connection"""
    join_room('admin_room')
    emit('status', {'msg': f'{current_user.username} has connected!'})
    logging.info(f"User {current_user.username} connected to WebSocket")

@socketio.on('disconnect')
@login_required
def handle_disconnect():
    """Handle client disconnection"""
    leave_room('admin_room')
    logging.info(f"User {current_user.username} disconnected from WebSocket")

@socketio.on('request_device_status')
@login_required
def handle_device_status_request():
    """Handle request for current device status"""
    try:
        devices = Device.query.all()
        device_status = []
        
        for device in devices:
            try:
                online = device_manager.is_device_online(device.ip_address)
                device.online_status = online
            except Exception as e:
                logging.warning(f"Could not check status for device {device.name}: {str(e)}")
                online = False
                device.online_status = False
            
            device_status.append({
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
                'online_status': online
            })
        
        db.session.commit()
        emit('device_status_update', {'devices': device_status})
        
    except Exception as e:
        logging.error(f"Error getting device status: {str(e)}")
        emit('error', {'message': 'Failed to get device status'})

def device_status_monitor():
    """Background task to monitor device status and emit updates"""
    from app import app
    while True:
        try:
            with app.app_context():
                devices = Device.query.all()
                device_status = []
                status_changed = False
                
                for device in devices:
                    online = device_manager.is_device_online(device.ip_address)
                    if device.online_status != online:
                        device.online_status = online
                        status_changed = True
                    
                    device_status.append({
                        'id': device.id,
                        'name': device.name,
                        'ip_address': device.ip_address,
                        'online_status': online
                    })
                
                if status_changed:
                    db.session.commit()
                    socketio.emit('device_status_update', {'devices': device_status}, room='admin_room')
            
            time.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            logging.error(f"Error in device status monitor: {str(e)}")
            time.sleep(30)

def start_device_monitor():
    """Start the device status monitoring thread"""
    monitor_thread = threading.Thread(target=device_status_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    logging.info("Device status monitor started")

@socketio.on('manual_device_sync')
@login_required
def handle_manual_device_sync(data):
    """Handle manual device synchronization"""
    try:
        device_id = data.get('device_id')
        device = Device.query.get(device_id)
        
        if not device:
            emit('error', {'message': 'Device not found'})
            return
        
        # Sync attendance logs
        logs_count = device_manager.sync_attendance_logs(device.ip_address, device.device_id)
        
        # Update last sync time
        from datetime import datetime
        device.last_sync = datetime.utcnow()
        db.session.commit()
        
        emit('sync_complete', {
            'device_id': device_id,
            'message': f'Synced {logs_count} logs from {device.name}',
            'last_sync': device.last_sync.strftime('%Y-%m-%d %H:%M')
        })
        
    except Exception as e:
        logging.error(f"Error in manual device sync: {str(e)}")
        emit('error', {'message': f'Sync failed: {str(e)}'})

@socketio.on('device_beep')
@login_required
def handle_device_beep(data):
    """Handle device beep request"""
    try:
        device_id = data.get('device_id')
        device = Device.query.get(device_id)
        
        if not device:
            emit('error', {'message': 'Device not found'})
            return
        
        success = device_manager.beep_device(device.ip_address)
        
        if success:
            emit('beep_complete', {
                'device_id': device_id,
                'message': f'Device {device.name} beeped successfully'
            })
        else:
            emit('error', {'message': f'Failed to beep device {device.name}'})
            
    except Exception as e:
        logging.error(f"Error beeping device: {str(e)}")
        emit('error', {'message': f'Beep failed: {str(e)}'})