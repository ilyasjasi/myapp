from flask import render_template, request, jsonify, redirect, url_for, flash, send_file
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
import pandas as pd
import io
import base64
import socket
from app import app, db
from models import *
from device_manager import DeviceManager
from utils import get_setting, set_setting
from cache_manager import get_device_info_cached, invalidate_device_cache, device_cache
import logging
import threading

device_manager = DeviceManager()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = AdminUser.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard/')
@login_required
def index():
    try:
        # Dashboard statistics - fast queries only with error handling
        try:
            total_devices = Device.query.count()
            logging.info(f"Dashboard: Found {total_devices} total devices")
        except Exception as e:
            logging.error(f"Error counting devices: {e}")
            total_devices = 0
            
        try:
            online_devices = Device.query.filter_by(online_status=True).count()
            logging.info(f"Dashboard: Found {online_devices} online devices")
        except Exception as e:
            logging.error(f"Error counting online devices: {e}")
            online_devices = 0
            
        try:
            total_users = User.query.filter_by(status='Active').count()
            logging.info(f"Dashboard: Found {total_users} active users")
        except Exception as e:
            logging.error(f"Error counting users: {e}")
            total_users = 0
            
        try:
            total_logs = AttendanceLog.query.count()
            logging.info(f"Dashboard: Found {total_logs} total logs")
        except Exception as e:
            logging.error(f"Error counting logs: {e}")
            total_logs = 0

        # Today's logs
        try:
            today = datetime.utcnow().date()
            today_start = datetime.combine(today, datetime.min.time())
            today_end = datetime.combine(today, datetime.max.time())
            today_logs = AttendanceLog.query.filter(
                AttendanceLog.timestamp >= today_start,
                AttendanceLog.timestamp <= today_end
            ).count()
            logging.info(f"Dashboard: Found {today_logs} logs today")
        except Exception as e:
            logging.error(f"Error counting today's logs: {e}")
            today_logs = 0

        # Yesterday's logs
        try:
            yesterday = today - timedelta(days=1)
            yesterday_start = datetime.combine(yesterday, datetime.min.time())
            yesterday_end = datetime.combine(yesterday, datetime.max.time())
            yesterday_logs = AttendanceLog.query.filter(
                AttendanceLog.timestamp >= yesterday_start,
                AttendanceLog.timestamp <= yesterday_end
            ).count()
            logging.info(f"Dashboard: Found {yesterday_logs} logs yesterday")
        except Exception as e:
            logging.error(f"Error counting yesterday's logs: {e}")
            yesterday_logs = 0

        # Recent logs with user info - limited query
        try:
            recent_logs_query = AttendanceLog.query.order_by(AttendanceLog.timestamp.desc()).limit(5).all()
            recent_logs = []
            for log in recent_logs_query:
                try:
                    user = User.query.filter_by(user_id=log.user_id).first()
                    device = Device.query.filter_by(device_id=log.device_id).first()
                    # Fix timestamp handling
                    timestamp_str = 'N/A'
                    if log.timestamp:
                        try:
                            if isinstance(log.timestamp, str):
                                timestamp_str = log.timestamp
                            else:
                                timestamp_str = log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        except Exception as e:
                            logging.error(f"Error formatting timestamp for log {log.id}: {e}")
                            timestamp_str = str(log.timestamp)
                    
                    recent_logs.append({
                        'timestamp': timestamp_str,
                        'user_id': log.user_id,
                        'user_name': f"{user.first_name} {user.last_name}" if user else 'Unknown',
                        'status': log.status or 'Unknown',
                        'device_name': device.name if device else 'Unknown',
                        'area': log.area or 'N/A'
                    })
                except Exception as e:
                    logging.error(f"Error processing recent log {log.id}: {e}")
                    continue
            logging.info(f"Dashboard: Loaded {len(recent_logs)} recent logs")
        except Exception as e:
            logging.error(f"Error loading recent logs: {e}")
            recent_logs = []

        # Device status - load basic info only, detailed info loaded via AJAX
        devices = Device.query.all()
        device_stats = []

        for device in devices:
            try:
                user_count = User.query.filter_by(device_id=device.device_id).count()
            except:
                user_count = 0
                
            try:
                log_count = AttendanceLog.query.filter_by(device_id=device.device_id).count()
            except:
                log_count = 0
            
            # Basic device info - detailed info loaded asynchronously
            device_info = {
                'device': device, 
                'user_count': user_count,
                'template_count': 0,  # Will be loaded via AJAX
                'face_count': 0,      # Will be loaded via AJAX
                'log_count': log_count
            }
            device_stats.append(device_info)

        stats = {
            'total_devices': total_devices,
            'online_devices': online_devices,
            'total_users': total_users,
            'total_logs': total_logs,
            'today_logs': today_logs,
            'yesterday_logs': yesterday_logs
        }

        logging.info(f"Dashboard stats: {stats}")
        return render_template('index.html', stats=stats, recent_logs=recent_logs, device_stats=device_stats)
    except Exception as e:
        logging.error(f"Error in index route: {str(e)}")
        # Return basic stats if there's an error
        stats = {
            'total_devices': 0,
            'online_devices': 0,
            'total_users': 0,
            'total_logs': 0,
            'today_logs': 0,
            'yesterday_logs': 0
        }
        return render_template('index.html', stats=stats, recent_logs=[], device_stats=[])

@app.route('/devices/')
@login_required
def devices():
    try:
        # Always fetch fresh data for now - caching SQLAlchemy objects can cause issues
        devices = Device.query.all()
        areas = Area.query.all()
        
        # Don't fetch device info synchronously - use lazy loading instead
        device_info = {}

        logging.info(f"Devices route: Found {len(devices)} devices")
        return render_template('devices.html', devices=devices, areas=areas, device_info=device_info)
    except Exception as e:
        logging.error(f"Error in devices route: {str(e)}")
        return render_template('devices.html', devices=[], areas=[], device_info={})

@app.route('/api/devices', methods=['POST'])
@login_required
def add_device():
    try:
        data = request.get_json()

        # Quick validation
        if not data.get('device_id') or not data.get('name') or not data.get('ip_address'):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400

        # Check if device already exists
        if Device.query.filter_by(device_id=data['device_id']).first():
            return jsonify({'success': False, 'message': 'Device ID already exists'}), 400

        # Create device record immediately
        device = Device(
            device_id=data['device_id'],
            name=data['name'],
            ip_address=data['ip_address'],
            area_id=data.get('area_id'),
            online_status=False  # Will be updated by background task
        )

        db.session.add(device)
        db.session.commit()

        # Invalidate device cache
        device_cache.delete('device_list')

        # Start background processing for device setup
        def background_device_setup():
            try:
                with app.app_context():
                    # Test connection and get device info
                    device_info = device_manager.get_device_info(data['ip_address'])
                    if device_info:
                        device.mac_address = device_info.get('mac_address')
                        device.serialnumber = device_info.get('serial_number')
                        device.online_status = True
                        db.session.commit()

                        # Auto-sync users from device (this will also auto-fetch logs)
                        users_synced = device_manager.sync_users_from_device(
                            data['ip_address'], data['device_id'], data.get('area_id')
                        )

                        # If no users were synced, still try to fetch logs
                        if users_synced == 0:
                            device_manager.sync_attendance_logs(data['ip_address'], data['device_id'])
                            
                        # Wait 2 minutes before starting sync to prevent crashes
                        time.sleep(120)
                        
                        # Push existing users and templates to new device
                        if data.get('area_id'):
                            logging.info(f"Pushing users to new device {data['name']}")
                            device_manager.push_users_to_device(data['ip_address'], data.get('area_id'))
                            logging.info(f"Pushing templates to new device {data['name']}")
                            device_manager.push_templates_to_device(data['ip_address'], data.get('area_id'))
                            
                        # Sync with other devices in the same area (bidirectional)
                        if data.get('area_id'):
                            logging.info(f"Syncing devices in area {data.get('area_id')}")
                            device_manager.sync_devices_in_area(data.get('area_id'))
                        
                        logging.info(f"Device {data['name']} setup completed in background")
                    else:
                        logging.warning(f"Could not connect to device {data['name']} during background setup")
            except Exception as e:
                logging.error(f"Background device setup error for {data['name']}: {str(e)}")

        # Start background thread
        setup_thread = threading.Thread(target=background_device_setup, daemon=True)
        setup_thread.start()

        return jsonify({
            'success': True, 
            'message': 'Device added successfully! Setup is continuing in background...', 
            'close_modal': True
        })
    except Exception as e:
        logging.error(f"Error adding device: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/devices/<int:device_id>', methods=['GET'])
@login_required
def get_device(device_id):
    try:
        device = Device.query.get_or_404(device_id)
        
        # Get device info from the actual device
        device_info = device_manager.get_device_info(device.ip_address)
        if device_info:
            return jsonify({
                'success': True,
                'device_info': {
                    'user_count': device_info.get('user_count', 0),
                    'template_count': device_info.get('template_count', 0),
                    'face_count': device_info.get('face_count', 0),
                    'log_count': device_info.get('log_count', 0),
                    'device_time': device_info.get('device_time').strftime('%H:%M:%S') if device_info.get('device_time') and hasattr(device_info.get('device_time'), 'strftime') else str(device_info.get('device_time', ''))
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Could not connect to device'
            }), 400
    except Exception as e:
        logging.error(f"Error getting device info: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/devices/<int:device_id>/logs', methods=['DELETE'])
@login_required
def delete_device_logs(device_id):
    try:
        device = Device.query.get_or_404(device_id)
        
        # Delete all logs for this device from database
        deleted_count = AttendanceLog.query.filter_by(device_id=device.device_id).delete()
        db.session.commit()
        
        logging.info(f"Deleted {deleted_count} logs for device {device.name}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully deleted {deleted_count} logs for device {device.name}'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting device logs: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/devices/<int:device_id>', methods=['PUT'])
@login_required
def update_device(device_id):
    try:
        device = Device.query.get_or_404(device_id)
        data = request.get_json()

        device.name = data['name']
        device.ip_address = data['ip_address']
        device.area_id = data.get('area_id')

        db.session.commit()

        return jsonify({'success': True, 'message': 'Device updated successfully', 'close_modal': True})
    except Exception as e:
        logging.error(f"Error updating device: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/devices/<int:device_id>', methods=['DELETE'])
@login_required
def delete_device(device_id):
    try:
        device = Device.query.get_or_404(device_id)
        db.session.delete(device)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Device deleted successfully'})
    except Exception as e:
        logging.error(f"Error deleting device: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/devices/<int:device_id>/sync')
@login_required
def sync_device(device_id):
    """Comprehensive device sync - users, templates, terminated user removal, logs"""
    try:
        device = Device.query.get_or_404(device_id)
        
        # Use enhanced comprehensive sync function 
        if device.area_id:
            # Use enhanced area-based sync for better template handling
            result = device_manager.sync_devices_in_area(device.area_id)
        else:
            # Fallback to individual device sync
            result = device_manager.comprehensive_device_sync(device.ip_address, device.area_id)
        
        if result.get('success'):
            device.last_sync = datetime.utcnow()
            db.session.commit()
            
            message = f"Sync completed: {result.get('users_collected', 0)} users collected, " \
                     f"{result.get('users_synced', 0)} users synced, " \
                     f"{result.get('templates_synced', 0)} templates, " \
                     f"{result.get('terminated_removed', 0)} terminated removed, " \
                     f"{result.get('logs_collected', 0)} logs collected"
            
            if result.get('time_synced'):
                message += ", time synced"
            
            if result.get('errors'):
                message += f" (with {len(result['errors'])} warnings)"
                
            return jsonify({
                'success': True, 
                'message': message,
                'details': result
            })
        else:
            return jsonify({
                'success': False, 
                'message': f"Sync failed: {result.get('error', 'Unknown error')}"
            }), 500
            
    except Exception as e:
        logging.error(f"Error syncing device: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/devices/<int:device_id>/set_time', methods=['POST'])
@login_required
def set_device_time(device_id):
    try:
        device = Device.query.get_or_404(device_id)
        data = request.get_json()

        if data.get('datetime'):
            target_time = datetime.fromisoformat(data['datetime'])
        else:
            target_time = datetime.now()

        success = device_manager.set_device_time(device.ip_address, target_time)

        if success:
            return jsonify({'success': True, 'message': 'Device time updated successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to update device time'})
    except Exception as e:
        logging.error(f"Error setting device time: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/devices/<int:device_id>/beep')
@login_required
def beep_device(device_id):
    try:
        device = Device.query.get_or_404(device_id)
        success = device_manager.beep_device(device.ip_address)

        if success:
            return jsonify({'success': True, 'message': 'Device beeped successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to beep device'})
    except Exception as e:
        logging.error(f"Error beeping device: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/devices/status')
@login_required
def devices_status():
    try:
        devices = Device.query.all()
        status_list = []

        for device in devices:
            # Check actual device status in real-time for more accurate results
            try:
                online = device_manager.is_device_online(device.ip_address)
                # Update database if status changed
                if device.online_status != online:
                    device.online_status = online
            except Exception as e:
                logging.error(f"Error checking device {device.name} status: {e}")
                online = device.online_status  # Fall back to cached status

            device_info = {
                'user_count': 0,
                'template_count': 0,
                'face_count': 0,
                'log_count': 0,
                'mac_address': device.mac_address or 'N/A',
                'serial_number': device.serialnumber or 'N/A'
            }

            # Only get detailed info for online devices using cache
            if online:
                info = get_device_info_cached(device_manager, device.ip_address, ttl=300)
                if info:
                    device_info.update({
                        'user_count': info.get('user_count', 0),
                        'template_count': info.get('template_count', 0),
                        'face_count': info.get('face_count', 0),
                        'log_count': info.get('log_count', 0),
                        'mac_address': info.get('mac_address', device.mac_address or 'N/A'),
                        'serial_number': info.get('serial_number', device.serialnumber or 'N/A')
                    })

                    # Update device info in database if missing
                    if not device.mac_address and info.get('mac_address'):
                        device.mac_address = info.get('mac_address')
                    if not device.serialnumber and info.get('serial_number'):
                        device.serialnumber = info.get('serial_number')

            status_list.append({
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
                'online_status': online,
                **device_info
            })

        db.session.commit()
        return jsonify(status_list)
    except Exception as e:
        logging.error(f"Error checking device status: {str(e)}")
        return jsonify([]), 500

@app.route('/api/devices/<int:device_id>/info')
@login_required
def get_device_info_async(device_id):
    """Get detailed device info asynchronously with caching"""
    try:
        device = Device.query.get_or_404(device_id)
        
        # First check basic TCP connectivity
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        tcp_ok = sock.connect_ex((device.ip_address, 4370)) == 0
        sock.close()
        
        if not tcp_ok:
            logging.warning(f"TCP connection to {device.ip_address} failed")
            return jsonify({
                'success': True,
                'data': {
                    'user_count': 0,
                    'template_count': 0,
                    'face_count': 0,
                    'log_count': 0,
                    'device_time': 'N/A',
                    'online': False
                }
            })
        
        # If TCP is OK but ZK handshake fails, return basic online status
        try:
            info = device_manager.get_device_info(device.ip_address)
            if not info:
                logging.warning(f"Got no info but TCP is up for {device.ip_address}, returning basic status")
                return jsonify({
                    'success': True,
                    'data': {
                        'user_count': 0,
                        'template_count': 0,
                        'face_count': 0,
                        'log_count': 0,
                        'device_time': 'N/A',
                        'online': True
                    }
                })
                
            return jsonify({
                'success': True,
                'data': {
                    'user_count': info.get('user_count', 0),
                    'template_count': info.get('template_count', 0),
                    'face_count': info.get('face_count', 0),
                    'log_count': info.get('log_count', 0),
                    'device_time': info.get('device_time', 'N/A'),
                    'online': True
                }
            })
            
        except Exception as e:
            logging.error(f"Error getting device info for {device.ip_address}: {e}")
            # Still return online=True if TCP is up but we couldn't get detailed info
            return jsonify({
                'success': True,
                'data': {
                    'user_count': 0,
                    'template_count': 0,
                    'face_count': 0,
                    'log_count': 0,
                    'device_time': 'N/A',
                    'online': True
                }
            })
            
    except Exception as e:
        logging.error(f"Error getting device info for device {device_id}: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


# Add these to your Flask app:

@app.route('/sync_monitor')
def sync_monitor():
    return render_template('sync_monitor.html')

@app.route('/api/manual/enhanced_device_sync', methods=['POST'])
@login_required
def manual_enhanced_sync():
    """Start enhanced device sync manually"""
    try:
        logging.info("Enhanced device sync requested via API")
        
        # Update sync status
        global sync_status_data
        sync_status_data['is_syncing'] = True
        sync_status_data['overall_progress'] = 0
        sync_status_data['users_progress'] = 0
        sync_status_data['fingerprint_progress'] = 0
        sync_status_data['face_progress'] = 0
        sync_status_data['current_activity'] = [{
            'timestamp': datetime.now().isoformat(),
            'type': 'info',
            'message': 'Enhanced sync starting...'
        }]
        
        # Import and validate
        try:
            from enhanced_device_sync import EnhancedDeviceSync
            logging.info("Enhanced sync module imported successfully")
        except ImportError as e:
            logging.error(f"Failed to import enhanced_device_sync: {e}")
            sync_status_data['is_syncing'] = False
            return jsonify({
                'success': False,
                'message': f'Enhanced sync module not available: {str(e)}'
            }), 500
        
        # Get devices
        try:
            devices = Device.query.filter_by(online_status=True).all()
            device_ips = [device.ip_address for device in devices]
            logging.info(f"Found {len(device_ips)} online devices: {device_ips}")
            
            if not device_ips:
                sync_status_data['is_syncing'] = False
                return jsonify({
                    'success': False,
                    'message': 'No online devices found for enhanced sync'
                }), 400
                
        except Exception as e:
            logging.error(f"Error querying devices: {e}")
            sync_status_data['is_syncing'] = False
            return jsonify({
                'success': False,
                'message': f'Database error: {str(e)}'
            }), 500
        
        # Start sync in background thread
        def run_sync():
            # Run within Flask app context to avoid database context errors
            with app.app_context():
                try:
                    logging.info("Starting enhanced sync thread")
                    
                    # Update status
                    sync_status_data['current_activity'].append({
                        'timestamp': datetime.now().isoformat(),
                        'type': 'info',
                        'message': f'Syncing {len(device_ips)} devices...'
                    })
                    
                    # Initialize sync manager within app context
                    sync_manager = EnhancedDeviceSync()
                    
                    # Define progress callback to update sync status
                    def progress_callback(message):
                        sync_status_data['current_activity'].append({
                            'timestamp': datetime.now().isoformat(),
                            'type': 'info',
                            'message': message
                        })
                        
                        # Update progress based on message content
                        if "Connecting to device" in message:
                            sync_status_data['overall_progress'] = 10
                        elif "Getting device data" in message:
                            sync_status_data['overall_progress'] = 20
                        elif "Removing" in message and "users" in message:
                            sync_status_data['overall_progress'] = 30
                            sync_status_data['users_progress'] = 25
                        elif "Syncing users" in message:
                            sync_status_data['overall_progress'] = 50
                            sync_status_data['users_progress'] = 50
                        elif "Syncing templates" in message:
                            sync_status_data['overall_progress'] = 70
                            sync_status_data['fingerprint_progress'] = 50
                        elif "Syncing face" in message:
                            sync_status_data['overall_progress'] = 85
                            sync_status_data['face_progress'] = 50
                        
                        logging.info(f"Enhanced sync progress: {message}")
                    
                    result = sync_manager.sync_specific_devices(device_ips, progress_callback)
                    
                    # Update final status
                    sync_status_data['is_syncing'] = False
                    sync_status_data['last_sync_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    if result['success']:
                        logging.info(f"Enhanced sync completed successfully: {result}")
                        sync_status_data['synced_devices'] = result.get('synced_devices', 0)
                        sync_status_data['users_synced'] = result.get('total_users_synced', 0)
                        sync_status_data['templates_synced'] = result.get('total_templates_synced', 0)
                        sync_status_data['face_templates_synced'] = result.get('total_face_templates_synced', 0)
                        sync_status_data['photos_synced'] = result.get('total_photos_synced', 0)
                        sync_status_data['users_added'] = result.get('total_users_added', 0)
                        sync_status_data['users_removed'] = result.get('total_users_removed', 0)
                        
                        # Set progress to 100% on completion
                        sync_status_data['overall_progress'] = 100
                        sync_status_data['users_progress'] = 100
                        sync_status_data['fingerprint_progress'] = 100
                        sync_status_data['face_progress'] = 100
                        
                        sync_status_data['current_activity'].append({
                            'timestamp': datetime.now().isoformat(),
                            'type': 'success',
                            'message': f'Enhanced sync completed successfully! Synced {result.get("synced_devices", 0)} devices'
                        })
                    else:
                        logging.error(f"Enhanced sync failed: {result}")
                        sync_status_data['current_activity'].append({
                            'timestamp': datetime.now().isoformat(),
                            'type': 'error',
                            'message': f'Enhanced sync failed: {result.get("message", "Unknown error")}'
                        })
                        
                except Exception as e:
                    logging.error(f"Error in enhanced sync thread: {e}")
                    sync_status_data['is_syncing'] = False
                    sync_status_data['current_activity'].append({
                        'timestamp': datetime.now().isoformat(),
                        'type': 'error',
                        'message': f'Sync error: {str(e)}'
                    })
        
        # Start sync in background
        sync_thread = threading.Thread(target=run_sync, daemon=True)
        sync_thread.start()
        logging.info("Enhanced sync thread started")
        
        return jsonify({
            'success': True,
            'message': 'Enhanced device sync started successfully'
        })
        
    except Exception as e:
        logging.error(f"Error starting enhanced sync: {e}")
        sync_status_data['is_syncing'] = False
        return jsonify({
            'success': False,
            'message': f'Failed to start enhanced sync: {str(e)}'
        }), 500

# Global sync status tracking
sync_status_data = {
    'is_syncing': False,
    'synced_devices': 0,
    'users_synced': 0,
    'templates_synced': 0,
    'face_templates_synced': 0,
    'photos_synced': 0,
    'users_added': 0,
    'users_removed': 0,
    'overall_progress': 0,
    'users_progress': 0,
    'fingerprint_progress': 0,
    'face_progress': 0,
    'current_activity': [],
    'last_sync_time': None,
    'sync_duration': None
}

@app.route('/api/sync/status')
@login_required
def sync_status():
    """Return current sync status for monitor"""
    return jsonify(sync_status_data)

@app.route('/api/sync/enhanced', methods=['POST'])
@login_required
def start_enhanced_sync():
    """Start enhanced sync from monitor"""
    return manual_enhanced_sync()  # Reuse the same logic

@app.route('/api/sync/basic', methods=['POST'])
@login_required
def start_basic_sync():
    """Start basic sync from monitor"""
    try:
        logging.info("Basic sync requested via API")
        
        # Update sync status
        global sync_status_data
        sync_status_data['is_syncing'] = True
        sync_status_data['current_activity'] = [{
            'timestamp': datetime.now().isoformat(),
            'type': 'info',
            'message': 'Basic sync starting...'
        }]
        
        # Get devices
        devices = Device.query.filter_by(online_status=True).all()
        device_ips = [device.ip_address for device in devices]
        
        if not device_ips:
            sync_status_data['is_syncing'] = False
            return jsonify({
                'success': False,
                'message': 'No online devices found for basic sync'
            }), 400
        
        # Start basic sync in background thread
        def run_basic_sync():
            try:
                logging.info(f"Starting basic sync for {len(device_ips)} devices")
                synced_count = 0
                
                for device in devices:
                    try:
                        sync_status_data['current_activity'].append({
                            'timestamp': datetime.now().isoformat(),
                            'type': 'info',
                            'message': f'Syncing device {device.ip_address}...'
                        })
                        
                        # Sync time
                        device_manager.sync_time_to_device(device.ip_address)
                        
                        # Sync users to device
                        device_manager.sync_users_to_device(device.ip_address, device.area_id)
                        
                        # Sync attendance logs from device
                        device_manager.sync_attendance_logs(device.ip_address, device.device_id)
                        
                        synced_count += 1
                        logging.info(f"Basic sync completed for device {device.ip_address}")
                        
                        sync_status_data['current_activity'].append({
                            'timestamp': datetime.now().isoformat(),
                            'type': 'success',
                            'message': f'Synced device {device.ip_address} (time, users, logs)'
                        })
                        
                    except Exception as e:
                        logging.error(f"Error syncing device {device.ip_address}: {e}")
                        sync_status_data['current_activity'].append({
                            'timestamp': datetime.now().isoformat(),
                            'type': 'error',
                            'message': f'Failed to sync {device.ip_address}: {str(e)}'
                        })
                
                # Update final status
                sync_status_data['is_syncing'] = False
                sync_status_data['synced_devices'] = synced_count
                sync_status_data['last_sync_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                sync_status_data['current_activity'].append({
                    'timestamp': datetime.now().isoformat(),
                    'type': 'success',
                    'message': f'Basic sync completed! Synced {synced_count} devices'
                })
                        
            except Exception as e:
                logging.error(f"Error in basic sync thread: {e}")
                sync_status_data['is_syncing'] = False
                sync_status_data['current_activity'].append({
                    'timestamp': datetime.now().isoformat(),
                    'type': 'error',
                    'message': f'Basic sync error: {str(e)}'
                })
        
        sync_thread = threading.Thread(target=run_basic_sync, daemon=True)
        sync_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Basic sync started successfully'
        })
        
    except Exception as e:
        logging.error(f"Error starting basic sync: {e}")
        sync_status_data['is_syncing'] = False
        return jsonify({
            'success': False,
            'message': f'Failed to start basic sync: {str(e)}'
        }), 500

@app.route('/api/sync/stop', methods=['POST'])
@login_required
def stop_sync():
    """Stop current sync operation"""
    try:
        # Reset sync status
        global sync_status_data
        sync_status_data['is_syncing'] = False
        
        return jsonify({
            'success': True,
            'message': 'Sync stop signal sent'
        })
        
    except Exception as e:
        logging.error(f"Error stopping sync: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to stop sync: {str(e)}'
        }), 500





@app.route('/api/cache/stats')
@login_required
def cache_stats():
    """Get cache statistics for monitoring"""
    try:
        stats = device_cache.get_stats()
        return jsonify({
            'success': True,
            'cache_stats': stats
        })
    except Exception as e:
        logging.error(f"Error getting cache stats: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/cache/clear', methods=['POST'])
@login_required
def clear_cache():
    """Clear device cache"""
    try:
        device_cache.clear()
        return jsonify({
            'success': True,
            'message': 'Cache cleared successfully'
        })
    except Exception as e:
        logging.error(f"Error clearing cache: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/users/')
@login_required
def users():
    try:
        # Get filter parameters
        area_filter = request.args.get('area')
        status_filter = request.args.get('status')
        site_filter = request.args.get('site')
        fingerprint_filter = request.args.get('fingerprint')
        face_filter = request.args.get('face')

        query = User.query

        if area_filter:
            query = query.filter_by(area_id=area_filter)
        if status_filter:
            query = query.filter_by(status=status_filter)
        if site_filter:
            query = query.filter_by(site=site_filter)
        if fingerprint_filter:
            query = query.filter_by(has_fingerprint=(fingerprint_filter == 'true'))
        if face_filter:
            query = query.filter_by(has_face=(face_filter == 'true'))

        users = query.all()
        areas = Area.query.all()
        
        # Get unique sites for filter
        try:
            sites = db.session.query(User.site).distinct().filter(User.site.isnot(None)).all()
            sites = [site[0] for site in sites if site[0]]
        except:
            sites = []
        
        return render_template('users.html', users=users, areas=areas, sites=sites)
    except Exception as e:
        logging.error(f"Error in users route: {str(e)}")
        # Return empty data if there's an error
        areas = Area.query.all() if Area.query.count() > 0 else []
        return render_template('users.html', users=[], areas=areas, sites=[])

@app.route('/api/users', methods=['POST'])
@login_required
def add_user():
    try:
        data = request.get_json()

        # Check if user_id already exists
        if User.query.filter_by(user_id=data['user_id']).first():
            return jsonify({'success': False, 'message': 'User ID already exists'})

        user = User(
            user_id=data['user_id'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            job_description=data.get('job_description'),
            status=data.get('status', 'Active'),
            area_id=data.get('area_id'),
            site=data.get('site'),
            has_fingerprint=False,
            has_face=False
        )

        db.session.add(user)
        db.session.commit()

        # Sync to devices in the same area with proper UID assignment
        synced_devices = 0
        if user.area_id:
            devices = Device.query.filter_by(area_id=user.area_id, online_status=True).all()
            for device in devices:
                try:
                    # Get next available UID for this device
                    next_uid = device_manager.get_next_available_uid(device.ip_address)
                    
                    # Add user to device with proper UID
                    conn = device_manager.connect_device(device.ip_address)
                    if conn:
                        conn.set_user(
                            uid=next_uid,
                            name=f"{user.first_name} {user.last_name}".strip(),
                            privilege=0,
                            password='',
                            group_id='',
                            user_id=user.user_id
                        )
                        synced_devices += 1
                        logging.info(f"Added user {user.user_id} to device {device.name} with UID {next_uid}")
                except Exception as e:
                    logging.error(f"Error syncing user to device {device.name}: {str(e)}")
                    continue

            message = f'User added successfully and synced to {synced_devices} devices'
        else:
            message = 'User added successfully (no area assigned for device sync)'

        return jsonify({
            'success': True, 
            'message': message,
            'close_modal': True
        })
    except Exception as e:
        logging.error(f"Error adding user: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['GET'])
@login_required
def get_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'user_id': user.user_id,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'job_description': user.job_description,
                'status': user.status,
                'area_id': user.area_id
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()

        user.first_name = data['first_name']
        user.last_name = data['last_name']
        user.job_description = data.get('job_description')
        user.status = data.get('status', 'Active')
        old_area_id = user.area_id
        user.area_id = data.get('area_id')

        db.session.commit()

        # Sync to devices if area changed
        if old_area_id != user.area_id:
            if old_area_id:
                old_devices = Device.query.filter_by(area_id=old_area_id, online_status=True).all()
                for device in old_devices:
                    device_manager.sync_users_to_device(device.ip_address, old_area_id)

            if user.area_id:
                new_devices = Device.query.filter_by(area_id=user.area_id, online_status=True).all()
                for device in new_devices:
                    device_manager.sync_users_to_device(device.ip_address, user.area_id)

        return jsonify({'success': True, 'message': 'User updated successfully'})
    except Exception as e:
        logging.error(f"Error updating user: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:user_id>/sync', methods=['POST'])
@login_required
def sync_user_to_devices(user_id):
    try:
        user = User.query.get_or_404(user_id)

        if user.area_id:
            devices = Device.query.filter_by(area_id=user.area_id, online_status=True).all()
            synced_count = 0

            for device in devices:
                try:
                    # Push specific user to device
                    device_manager.push_single_user_to_device(device.ip_address, user.user_id)
                    # Push user's templates to device
                    device_manager.push_user_templates_to_device(device.ip_address, user.user_id)
                    synced_count += 1
                    logging.info(f"Synced user {user.user_id} and templates to device {device.name}")
                except Exception as e:
                    logging.error(f"Error syncing user {user.user_id} to device {device.name}: {e}")
                    continue

            return jsonify({'success': True, 'message': f'User synced to {synced_count} devices'})
        else:
            return jsonify({'success': False, 'message': 'User has no area assigned'})
    except Exception as e:
        logging.error(f"Error syncing user to devices: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manual/sync_users_from_devices', methods=['POST'])
@login_required
def manual_sync_users_from_devices():
    try:
        devices = Device.query.filter_by(online_status=True).all()
        total_users = 0

        for device in devices:
            try:
                users_count = device_manager.sync_users_from_device(device.ip_address, device.device_id, device.area_id)
                total_users += users_count
            except Exception as e:
                logging.error(f"Error syncing users from device {device.name}: {str(e)}")
                continue

        return jsonify({'success': True, 'message': f'Synced {total_users} users from all devices'})
    except Exception as e:
        logging.error(f"Error in manual user sync: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/export/<table_name>')
@login_required
def export_table(table_name):
    try:
        output = io.BytesIO()

        if table_name == 'devices':
            devices = Device.query.all()
            data = []
            for device in devices:
                data.append({
                    'Device ID': device.device_id,
                    'Name': device.name,
                    'IP Address': device.ip_address,
                    'MAC Address': device.mac_address,
                    'Serial Number': device.serialnumber,
                    'Area': device.area_obj.name if device.area_obj else '',
                    'Online Status': 'Online' if device.online_status else 'Offline',
                    'Last Sync': device.last_sync.strftime('%Y-%m-%d %H:%M:%S') if device.last_sync else ''
                })

        elif table_name == 'users':
            users = User.query.all()
            data = []
            for user in users:
                data.append({
                    'User ID': user.user_id,
                    'First Name': user.first_name,
                    'Last Name': user.last_name,
                    'Job Description': user.job_description,
                    'Status': user.status,
                    'Area': user.area_obj.name if user.area_obj else '',
                    'Site': user.site or '',
                    'Has Fingerprint': 'Yes' if user.has_fingerprint else 'No',
                    'Has Face': 'Yes' if user.has_face else 'No'
                })

        elif table_name == 'logs':
            # Get filter parameters
            device_id = request.args.get('device_id')
            area_id = request.args.get('area_id')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            exported = request.args.get('exported')

            query = AttendanceLog.query

            if device_id:
                query = query.filter(AttendanceLog.device_id == device_id)

            if area_id:
                query = query.filter(AttendanceLog.area == area_id)

            if start_date:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(AttendanceLog.timestamp >= start_dt)

            if end_date:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(AttendanceLog.timestamp < end_dt)

            if exported:
                query = query.filter(AttendanceLog.exported_flag == (exported == 'true'))

            logs = query.order_by(AttendanceLog.timestamp.desc()).all()
            data = []
            for log in logs:
                user = User.query.filter_by(user_id=log.user_id).first()
                device = Device.query.filter_by(device_id=log.device_id).first()
                data.append({
                    'User ID': log.user_id,
                    'User Name': f"{user.first_name} {user.last_name}" if user else 'Unknown',
                    'Device ID': log.device_id,
                    'Device Name': device.name if device else 'Unknown',
                    'Area': log.area,
                    'Date': log.timestamp.strftime('%Y-%m-%d'),
                    'Time': log.timestamp.strftime('%H:%M:%S'),
                    'Status': log.status,
                    'Exported': 'Yes' if log.exported_flag else 'No'
                })

        elif table_name == 'areas':
            areas = Area.query.all()
            data = []
            for area in areas:
                data.append({
                    'Area ID': area.id,
                    'Area Name': area.name,
                    'Device Count': area.devices.count(),
                    'User Count': area.users.count()
                })

        elif table_name == 'admin_users':
            admin_users = AdminUser.query.all()
            data = []
            for admin in admin_users:
                data.append({
                    'Username': admin.username,
                    'Force Password Change': 'Yes' if admin.force_change else 'No'
                })

        else:
            return jsonify({'error': 'Invalid table name'}), 400

        df = pd.DataFrame(data)
        df.to_excel(output, index=False)
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'{table_name}_export.xlsx'
        )

    except Exception as e:
        logging.error(f"Error exporting {table_name}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/logs/')
@login_required
def logs():
    try:
        # Show empty logs page - data will be loaded via filters
        devices = Device.query.all()
        areas = Area.query.all()
        return render_template('logs.html', devices=devices, areas=areas, logs=[])
    except Exception as e:
        logging.error(f"Error in logs route: {str(e)}")
        return render_template('logs.html', devices=[], areas=[], logs=[])

@app.route('/api/logs')
@login_required
def get_logs():
    try:
        # Get filter parameters
        user_id = request.args.get('user_id')
        device_id = request.args.get('device_id')
        area_id = request.args.get('area_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        exported = request.args.get('exported')
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)  # Limit max per_page

        # Use optimized query with joins to reduce N+1 queries
        query = db.session.query(
            AttendanceLog.id,
            AttendanceLog.user_id,
            AttendanceLog.device_id,
            AttendanceLog.area,
            AttendanceLog.timestamp,
            AttendanceLog.status,
            AttendanceLog.exported_flag,
            User.first_name,
            User.last_name,
            Device.name.label('device_name')
        ).outerjoin(User, AttendanceLog.user_id == User.user_id)\
         .outerjoin(Device, AttendanceLog.device_id == Device.device_id)

        if user_id:
            query = query.filter(AttendanceLog.user_id.like(f'%{user_id}%'))

        if device_id:
            query = query.filter(AttendanceLog.device_id == device_id)

        if area_id:
            query = query.filter(AttendanceLog.area == area_id)

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(AttendanceLog.timestamp >= start_dt)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(AttendanceLog.timestamp < end_dt)
            except ValueError:
                pass

        if exported:
            query = query.filter(AttendanceLog.exported_flag == (exported == 'true'))

        # Use optimized ordering and pagination
        logs = query.order_by(AttendanceLog.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        logs_data = []
        for log in logs.items:
            logs_data.append({
                'id': log.id,
                'user_id': log.user_id,
                'user_name': f"{log.first_name} {log.last_name}" if log.first_name else 'Unknown',
                'device_id': log.device_id,
                'device_name': log.device_name or 'Unknown',
                'area': log.area,
                'date': log.timestamp.strftime('%Y-%m-%d'),
                'time': log.timestamp.strftime('%H:%M:%S'),
                'status': log.status,
                'exported': log.exported_flag
            })

        return jsonify({
            'logs': logs_data,
            'pagination': {
                'page': logs.page,
                'pages': logs.pages,
                'per_page': logs.per_page,
                'total': logs.total,
                'has_next': logs.has_next,
                'has_prev': logs.has_prev
            }
        })

    except Exception as e:
        logging.error(f"Error getting logs: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/database')
@app.route('/database/')
@login_required
def database_management():
    return render_template('database.html')

@app.route('/api/database/tables')
@login_required
def get_tables():
    try:
        tables = []
        
        # Safely get counts for each table
        try:
            tables.append({'name': 'devices', 'count': Device.query.count()})
        except Exception as e:
            logging.error(f"Error counting devices: {e}")
            tables.append({'name': 'devices', 'count': 0})
            
        try:
            tables.append({'name': 'users', 'count': User.query.count()})
        except Exception as e:
            logging.error(f"Error counting users: {e}")
            tables.append({'name': 'users', 'count': 0})
            
        try:
            tables.append({'name': 'logs', 'count': AttendanceLog.query.count()})
        except Exception as e:
            logging.error(f"Error counting logs: {e}")
            tables.append({'name': 'logs', 'count': 0})
            
        try:
            tables.append({'name': 'areas', 'count': Area.query.count()})
        except Exception as e:
            logging.error(f"Error counting areas: {e}")
            tables.append({'name': 'areas', 'count': 0})
            
        try:
            tables.append({'name': 'admin_users', 'count': AdminUser.query.count()})
        except Exception as e:
            logging.error(f"Error counting admin_users: {e}")
            tables.append({'name': 'admin_users', 'count': 0})
        
        return jsonify(tables)
    except Exception as e:
        logging.error(f"Error in get_tables: {str(e)}")
        return jsonify([]), 500

@app.route('/api/database/clear/<table_name>', methods=['POST'])
@login_required
def clear_table(table_name):
    try:
        if table_name == 'devices':
            Device.query.delete()
        elif table_name == 'users':
            User.query.delete()
        elif table_name == 'logs':
            AttendanceLog.query.delete()
        elif table_name == 'areas':
            Area.query.delete()
        elif table_name == 'admin_users':
            AdminUser.query.delete()
        else:
            return jsonify({'success': False, 'message': 'Invalid table name'})

        db.session.commit()
        return jsonify({'success': True, 'message': f'Table {table_name} cleared successfully'})
    except Exception as e:
        logging.error(f"Error clearing table {table_name}: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/settings')
@app.route('/settings/', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        csv_export_path = request.form.get('csv_export_path', '/tmp/ZKHours.csv')
        employee_csv_path = request.form.get('employee_csv_path', '/tmp/employees.csv')
        terminated_csv_path = request.form.get('terminated_csv_path', '/tmp/terminated.csv')
        csv_export_interval = request.form.get('csv_export_interval', '30')
        employee_sync_time = request.form.get('employee_sync_time', '00:00')
        terminate_sync_time = request.form.get('terminate_sync_time', '01:00')
        device_sync_interval = request.form.get('device_sync_interval', '60')

        set_setting('csv_export_path', csv_export_path)
        set_setting('employee_csv_path', employee_csv_path)
        set_setting('terminated_csv_path', terminated_csv_path)
        set_setting('csv_export_interval', csv_export_interval)
        set_setting('employee_sync_time', employee_sync_time)
        set_setting('terminate_sync_time', terminate_sync_time)
        set_setting('device_sync_interval', device_sync_interval)

        # Restart scheduler to apply new settings
        try:
            from scheduler_health_monitor import SchedulerHealthMonitor
            monitor = SchedulerHealthMonitor()
            monitor.restart_scheduler()
            logging.info("Scheduler restarted with new settings")
        except Exception as scheduler_error:
            logging.error(f"Error restarting scheduler: {scheduler_error}")

        flash('Settings saved successfully', 'success')
        return redirect(url_for('settings'))

    settings = {
        'csv_export_path': get_setting('csv_export_path', '/tmp/ZKHours.csv'),
        'employee_csv_path': get_setting('employee_csv_path', '/tmp/employees.csv'),
        'terminated_csv_path': get_setting('terminated_csv_path', '/tmp/terminated.csv'),
        'csv_export_interval': get_setting('csv_export_interval', '30'),
        'employee_sync_time': get_setting('employee_sync_time', '00:00'),
        'terminate_sync_time': get_setting('terminate_sync_time', '01:00'),
        'device_sync_interval': get_setting('device_sync_interval', '60')
    }

    return render_template('settings.html', settings=settings)

@app.route('/api/areas', methods=['GET', 'POST'])
@login_required
def areas_api():
    if request.method == 'POST':
        data = request.get_json()
        area = Area(name=data['name'])
        db.session.add(area)
        db.session.commit()
        return jsonify({'success': True, 'id': area.id, 'name': area.name})

    areas = Area.query.all()
    return jsonify([{'id': a.id, 'name': a.name} for a in areas])

@app.route('/admin_users/')
@login_required
def admin_users():
    users = AdminUser.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/api/admin_users', methods=['POST'])
@login_required
def add_admin_user():
    try:
        data = request.get_json()

        if AdminUser.query.filter_by(username=data['username']).first():
            return jsonify({'success': False, 'message': 'Username already exists'})

        user = AdminUser(
            username=data['username'],
            password_hash=generate_password_hash(data['password']),
            force_change=data.get('force_change', False)
        )

        db.session.add(user)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Admin user added successfully'})
    except Exception as e:
        logging.error(f"Error adding admin user: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin_users/<int:user_id>', methods=['PUT'])
@login_required
def update_admin_user(user_id):
    try:
        user = AdminUser.query.get_or_404(user_id)
        data = request.get_json()

        if user.id == current_user.id and data.get('username') != user.username:
            return jsonify({'success': False, 'message': 'Cannot change your own username'})

        user.username = data['username']
        if data.get('password'):
            user.password_hash = generate_password_hash(data['password'])
        user.force_change = data.get('force_change', False)

        db.session.commit()

        return jsonify({'success': True, 'message': 'Admin user updated successfully'})
    except Exception as e:
        logging.error(f"Error updating admin user: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin_users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_admin_user(user_id):
    try:
        user = AdminUser.query.get_or_404(user_id)

        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot delete your own account'})

        if AdminUser.query.count() <= 1:
            return jsonify({'success': False, 'message': 'Cannot delete the last admin user'})

        db.session.delete(user)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Admin user deleted successfully'})
    except Exception as e:
        logging.error(f"Error deleting admin user: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Manual operation endpoints
@app.route('/manual_export_csv', methods=['POST'])
@login_required
def manual_export_csv():
    try:
        import subprocess
        import json
        import sqlite3
        from datetime import datetime
        
        # Log job start
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        job_id = f"manual_csv_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, (job_id, 'Manual CSV Export', 'running', datetime.now().isoformat()))
        conn.commit()
        
        # Run CSV export via scheduler service
        result = subprocess.run(['python', '-c', 
            'from scheduler_service import SchedulerService; s = SchedulerService(); s.export_attendance_csv_job()'], 
            capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            cursor.execute("""
                UPDATE job_executions 
                SET status = 'completed', end_time = ?, result_data = ?
                WHERE job_id = ?
            """, (datetime.now().isoformat(), '{"manual_run": true}', job_id))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'CSV export completed successfully'})
        else:
            cursor.execute("""
                UPDATE job_executions 
                SET status = 'failed', end_time = ?, error_message = ?
                WHERE job_id = ?
            """, (datetime.now().isoformat(), result.stderr, job_id))
            conn.commit()
            conn.close()
            return jsonify({'success': False, 'message': f'CSV export failed: {result.stderr}'})
    except Exception as e:
        logging.error(f"Error in manual CSV export: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/manual_sync_employees', methods=['POST'])
@login_required
def manual_sync_employees():
    try:
        import subprocess
        import json
        import sqlite3
        from datetime import datetime
        
        # Log job start
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        job_id = f"manual_employee_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, (job_id, 'Manual Employee Import', 'running', datetime.now().isoformat()))
        conn.commit()
        
        # Run employee import via scheduler service
        result = subprocess.run(['python', '-c', 
            'from scheduler_service import SchedulerService; s = SchedulerService(); s.import_employee_data_job()'], 
            capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            cursor.execute("""
                UPDATE job_executions 
                SET status = 'completed', end_time = ?, result_data = ?
                WHERE job_id = ?
            """, (datetime.now().isoformat(), '{"manual_run": true}', job_id))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'Employee synchronization completed successfully'})
        else:
            cursor.execute("""
                UPDATE job_executions 
                SET status = 'failed', end_time = ?, error_message = ?
                WHERE job_id = ?
            """, (datetime.now().isoformat(), result.stderr, job_id))
            conn.commit()
            conn.close()
            return jsonify({'success': False, 'message': f'Employee sync failed: {result.stderr}'})
    except Exception as e:
        logging.error(f"Error in manual employee sync: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/manual_process_terminated', methods=['POST'])
@login_required
def manual_process_terminated():
    try:
        import subprocess
        import json
        import sqlite3
        from datetime import datetime
        
        # Log job start
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        job_id = f"manual_employee_terminate_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, (job_id, 'Manual Employee Termination', 'running', datetime.now().isoformat()))
        conn.commit()
        
        # Run employee termination via scheduler service
        result = subprocess.run(['python', '-c', 
            'from scheduler_service import SchedulerService; s = SchedulerService(); s.terminate_employees_job()'], 
            capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            cursor.execute("""
                UPDATE job_executions 
                SET status = 'completed', end_time = ?, result_data = ?
                WHERE job_id = ?
            """, (datetime.now().isoformat(), '{"manual_run": true}', job_id))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'Terminated employees processed successfully'})
        else:
            cursor.execute("""
                UPDATE job_executions 
                SET status = 'failed', end_time = ?, error_message = ?
                WHERE job_id = ?
            """, (datetime.now().isoformat(), result.stderr, job_id))
            conn.commit()
            conn.close()
            return jsonify({'success': False, 'message': f'Employee termination failed: {result.stderr}'})
    except Exception as e:
        logging.error(f"Error processing terminated employees: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manual/process_terminated', methods=['POST'])
@login_required
def api_manual_process_terminated():
    try:
        import subprocess
        import json
        import sqlite3
        from datetime import datetime
        
        # Log job start
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, ('manual_terminate', 'Manual Employee Termination', 'running', datetime.now().isoformat()))
        execution_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Run termination job via subprocess
        result = subprocess.run([
            'python', '-c', 
            'from scheduler_service import SchedulerService; s = SchedulerService(); s.terminate_employees_job()'
        ], capture_output=True, text=True, timeout=60)
        
        # Update job execution
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        if result.returncode == 0:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, result_data = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), 'completed', 
                  json.dumps({'message': 'Manual termination completed'}), execution_id))
            message = 'Employee termination process completed successfully'
        else:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, error_message = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), 'failed', result.stderr, execution_id))
            message = f'Employee termination failed: {result.stderr}'
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': result.returncode == 0, 'message': message})
        
    except Exception as e:
        logging.error(f"Error in manual termination: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manual/sync_employees', methods=['POST'])
@login_required
def api_manual_sync_employees():
    try:
        import subprocess
        import json
        import sqlite3
        from datetime import datetime
        
        # Log job start
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, ('manual_import', 'Manual Employee Import', 'running', datetime.now().isoformat()))
        execution_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Run import job via subprocess
        result = subprocess.run([
            'python', '-c', 
            'from scheduler_service import SchedulerService; s = SchedulerService(); s.import_employee_data_job()'
        ], capture_output=True, text=True, timeout=60)
        
        # Update job execution
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        if result.returncode == 0:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, result_data = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), 'completed', 
                  json.dumps({'message': 'Manual import completed'}), execution_id))
            message = 'Employee import process completed successfully'
        else:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, error_message = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), 'failed', result.stderr, execution_id))
            message = f'Employee import failed: {result.stderr}'
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': result.returncode == 0, 'message': message})
        
    except Exception as e:
        logging.error(f"Error in manual employee import: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manual/balance_devices', methods=['POST'])
@login_required
def api_manual_balance_devices():
    try:
        import json
        import sqlite3
        from datetime import datetime
        
        # Log job start
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO job_executions (job_id, job_name, status, start_time)
            VALUES (?, ?, ?, ?)
        """, ('manual_balance', 'Manual Device Balance', 'running', datetime.now().isoformat()))
        execution_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Run device balancing
        result = device_manager.balance_devices_in_area()
        
        # Update job execution
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        if result:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, result_data = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), 'completed', 
                  json.dumps(result), execution_id))
            message = f"Device balancing completed: {result.get('synced_users', 0)} users, {result.get('synced_templates', 0)} templates synced"
        else:
            cursor.execute("""
                UPDATE job_executions 
                SET end_time = ?, status = ?, error_message = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), 'failed', 'Device balancing failed', execution_id))
            message = 'Device balancing failed'
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': bool(result), 'message': message, 'result': result})
        
    except Exception as e:
        logging.error(f"Error in manual device balancing: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manual/sync_all_devices', methods=['POST'])
@login_required
def manual_sync_all_devices():
    """Comprehensive sync for all online devices - users, templates, terminated user removal"""
    try:
        devices = Device.query.filter_by(online_status=True).all()
        total_results = {
            'synced_devices': 0,
            'total_users_collected': 0,
            'total_users_synced': 0,
            'total_templates_synced': 0,
            'total_terminated_removed': 0,
            'total_logs_collected': 0,
            'total_devices': len(devices),
            'errors': []
        }

        for device in devices:
            try:
                logging.info(f"Starting comprehensive sync for device {device.name}")
                # Use enhanced area-based sync if device has area, otherwise individual sync
                if device.area_id:
                    result = device_manager.sync_devices_in_area(device.area_id)
                else:
                    result = device_manager.comprehensive_device_sync(device.ip_address, device.area_id)
                
                if result.get('success'):
                    total_results['synced_devices'] += 1
                    total_results['total_users_collected'] += result.get('users_collected', 0)
                    total_results['total_users_synced'] += result.get('users_synced', 0)
                    total_results['total_templates_synced'] += result.get('templates_synced', 0)
                    total_results['total_terminated_removed'] += result.get('terminated_removed', 0)
                    total_results['total_logs_collected'] += result.get('logs_collected', 0)
                    
                    # Update last sync time
                    device.last_sync = datetime.utcnow()
                    
                    logging.info(f"Completed sync for {device.name}: "
                               f"{result.get('users_collected', 0)} users collected, "
                               f"{result.get('users_synced', 0)} users synced, "
                               f"{result.get('templates_synced', 0)} templates, "
                               f"{result.get('terminated_removed', 0)} terminated removed")
                else:
                    error_msg = f"{device.name}: {result.get('error', 'Unknown error')}"
                    total_results['errors'].append(error_msg)
                    logging.error(f"Failed to sync device {device.name}: {result.get('error')}")
                    
            except Exception as e:
                error_msg = f"{device.name}: {str(e)}"
                total_results['errors'].append(error_msg)
                logging.error(f"Error syncing device {device.name}: {str(e)}")
                continue

        db.session.commit()
        
        message = f"Synchronized {total_results['synced_devices']}/{total_results['total_devices']} devices: " \
                 f"{total_results['total_users_collected']} users collected, " \
                 f"{total_results['total_users_synced']} users synced, " \
                 f"{total_results['total_templates_synced']} templates, " \
                 f"{total_results['total_terminated_removed']} terminated removed, " \
                 f"{total_results['total_logs_collected']} logs collected"
        
        if total_results['errors']:
            message += f" (with {len(total_results['errors'])} errors)"
            
        return jsonify({
            'success': True, 
            'message': message,
            'details': total_results
        })
        
    except Exception as e:
        logging.error(f"Error in manual device sync: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manual/refresh_all_logs', methods=['POST'])
@login_required
def manual_refresh_all_logs():
    try:
        devices = Device.query.filter_by(online_status=True).all()
        total_logs = 0

        for device in devices:
            try:
                logs_count = device_manager.sync_attendance_logs(device.ip_address, device.device_id)
                total_logs += logs_count
                device.last_sync = datetime.utcnow()
            except Exception as e:
                logging.error(f"Error refreshing logs from device {device.name}: {str(e)}")
                continue

        db.session.commit()
        return jsonify({'success': True, 'message': f'Refreshed {total_logs} attendance logs from all devices'})
    except Exception as e:
        logging.error(f"Error refreshing all logs: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manual/sync_templates', methods=['POST'])
@login_required
def manual_sync_templates():
    try:
        areas = Area.query.all()
        synced_count = 0

        for area in areas:
            if device_manager.sync_devices_in_area(area.id):
                synced_count += 1

        return jsonify({'success': True, 'message': f'Synchronized users and templates across {synced_count} areas'})
    except Exception as e:
        logging.error(f"Error syncing templates: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/areas/<int:area_id>/sync_devices', methods=['POST'])
@login_required
def sync_area_devices(area_id):
    try:
        success = device_manager.sync_devices_in_area(area_id)
        if success:
            return jsonify({'success': True, 'message': 'Devices synchronized successfully'})
        else:
            return jsonify({'success': False, 'message': 'Synchronization failed'})
    except Exception as e:
        logging.error(f"Error syncing area devices: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/bulk_update', methods=['POST'])
@login_required
def bulk_update_users():
    try:
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        updates = data.get('updates', {})

        if not user_ids:
            return jsonify({'success': False, 'message': 'No users selected'})

        updated_count = 0
        for user_id in user_ids:
            user = User.query.get(user_id)
            if user:
                for field, value in updates.items():
                    if hasattr(user, field):
                        setattr(user, field, value)
                        updated_count += 1

        db.session.commit()
        return jsonify({'success': True, 'message': f'Updated {updated_count} users'})
    except Exception as e:
        logging.error(f"Error bulk updating users: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/reports')
@app.route('/reports/')
@login_required
def reports():
    return render_template('reports.html')

@app.route('/reports/scheduler')
@login_required
def scheduler_info():
    """Show scheduler job information and schedule details"""
    try:
        import sqlite3
        import json
        from datetime import datetime
        
        # Get scheduler status from database
        conn = sqlite3.connect('instance/attendance.db')
        cursor = conn.cursor()
        
        # Get schedule settings from database
        cursor.execute("SELECT key, value FROM app_settings WHERE key IN (?, ?, ?, ?)", 
                      ('csv_export_interval', 'employee_sync_time', 'terminate_sync_time', 'device_sync_interval'))
        settings_rows = cursor.fetchall()
        settings = {row[0]: row[1] for row in settings_rows}
        
        # Check if scheduler service is running using a more reliable method
        import subprocess
        import psutil
        scheduler_running = False
        scheduler_pid = None
        
        try:
            # Check using psutil for running processes
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and 'scheduler_service.py' in ' '.join(cmdline):
                        scheduler_running = True
                        scheduler_pid = proc.info['pid']
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            # Fallback to subprocess method if psutil not available
            try:
                result = subprocess.run(['python', 'start_scheduler.py', 'status'], 
                                      capture_output=True, text=True, timeout=5)
                scheduler_running = result.returncode == 0
            except:
                scheduler_running = False
        
        # Build schedule details
        schedule_jobs = [
            {
                'id': 'csv_export',
                'name': 'CSV Export',
                'description': 'Export attendance logs to CSV file',
                'trigger': f"Every {settings.get('csv_export_interval', '30')} minutes",
                'status': 'Active' if scheduler_running else 'Inactive',
                'type': 'interval'
            },
            {
                'id': 'employee_import',
                'name': 'Employee Import',
                'description': 'Import employee data from CSV',
                'trigger': f"Daily at {settings.get('employee_sync_time', '00:00')}",
                'status': 'Active' if scheduler_running else 'Inactive',
                'type': 'daily'
            },
            {
                'id': 'employee_termination',
                'name': 'Employee Termination',
                'description': 'Process terminated employees',
                'trigger': f"Daily at {settings.get('terminate_sync_time', '01:00')}",
                'status': 'Active' if scheduler_running else 'Inactive',
                'type': 'daily'
            },
            {
                'id': 'device_sync',
                'name': 'Device Sync',
                'description': 'Sync users, templates, and logs from devices (3 devices per cycle)',
                'trigger': f"Every {settings.get('device_sync_interval', '5')} minutes",
                'status': 'Active' if scheduler_running else 'Inactive',
                'type': 'interval'
            },
            {
                'id': 'health_check',
                'name': 'Health Check',
                'description': 'Monitor scheduler service health',
                'trigger': 'Every 5 minutes',
                'status': 'Active' if scheduler_running else 'Inactive',
                'type': 'interval'
            }
        ]
        
        # Get recent job executions for history
        cursor.execute("""
            SELECT job_id, job_name, status, start_time, end_time, error_message, result_data
            FROM job_executions 
            ORDER BY start_time DESC 
            LIMIT 10
        """)
        execution_history = cursor.fetchall()
        
        scheduler_data = {
            'running': scheduler_running,
            'pid': scheduler_pid,
            'schedule_jobs': schedule_jobs,
            'execution_history': [
                {
                    'id': job[0],
                    'name': job[1],
                    'status': job[2],
                    'start_time': job[3],
                    'end_time': job[4],
                    'error_message': job[5],
                    'result_data': job[6]
                } for job in execution_history
            ]
        }
        
        conn.close()
        return render_template('scheduler_info.html', scheduler_data=scheduler_data)
        
    except Exception as e:
        logging.error(f"Error getting scheduler info: {e}")
        return render_template('scheduler_info.html', scheduler_data={'error': str(e)})

@app.route('/api/scheduler/control', methods=['POST'])
@login_required
def scheduler_control():
    """Control scheduler service (start/stop/restart)"""
    try:
        data = request.get_json()
        action = data.get('action')
        
        if action not in ['start', 'stop', 'restart']:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        import subprocess
        
        try:
            result = subprocess.run(
                ['python', 'start_scheduler.py', action],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                message = f'Scheduler {action} completed successfully'
                if action == 'start':
                    message = 'Scheduler started successfully'
                elif action == 'stop':
                    message = 'Scheduler stopped successfully'
                elif action == 'restart':
                    message = 'Scheduler restarted successfully'
                    
                return jsonify({'success': True, 'message': message})
            else:
                error_msg = result.stderr or result.stdout or f'Failed to {action} scheduler'
                return jsonify({'success': False, 'message': error_msg})
                
        except subprocess.TimeoutExpired:
            return jsonify({'success': False, 'message': f'Scheduler {action} timed out'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
            
    except Exception as e:
        logging.error(f"Error controlling scheduler: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/reports/error_logs')
@login_required
def error_logs():
    """Show error logs from database (last 7 days)"""
    try:
        from datetime import datetime, timedelta
        from models import ErrorLog
        from collections import Counter
        
        # Get logs from last 7 days
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        today = datetime.utcnow().date()
        
        # Query error logs from database
        logs_query = ErrorLog.query.filter(
            ErrorLog.timestamp >= seven_days_ago,
            ErrorLog.level.in_(['ERROR', 'WARNING'])
        ).order_by(ErrorLog.timestamp.desc()).limit(500)  # Limit to prevent performance issues
        
        error_logs_db = logs_query.all()
        
        # Convert to list format for template
        error_logs = []
        error_messages = []
        error_stats = {
            'total_errors': 0,
            'total_warnings': 0,
            'today_errors': 0,
            'most_common_error': ''
        }
        
        for log in error_logs_db:
            error_logs.append({
                'timestamp': log.timestamp,
                'level': log.level,
                'module': log.module or 'Unknown',
                'message': log.message or 'No message'
            })
            
            error_messages.append(log.message or 'No message')
            
            if log.level == 'ERROR':
                error_stats['total_errors'] += 1
            elif log.level == 'WARNING':
                error_stats['total_warnings'] += 1
                
            if log.timestamp.date() == today:
                error_stats['today_errors'] += 1
        
        # Add scheduler logs from file
        try:
            import re
            scheduler_log_path = 'scheduler_service.log'
            if os.path.exists(scheduler_log_path):
                with open(scheduler_log_path, 'r') as f:
                    lines = f.readlines()
                    
                # Parse recent scheduler logs (last 200 lines)
                for line in lines[-200:]:
                    if 'ERROR' in line or 'WARNING' in line:
                        try:
                            # Parse log format: 2025-09-10 08:34:53,883 - SCHEDULER - ERROR - message
                            match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - SCHEDULER - (ERROR|WARNING) - (.+)', line.strip())
                            if match:
                                timestamp_str, level, message = match.groups()
                                log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                                
                                # Only include recent logs (last 7 days)
                                if log_time >= seven_days_ago:
                                    error_logs.append({
                                        'timestamp': log_time,
                                        'level': level,
                                        'module': 'SCHEDULER',
                                        'message': message
                                    })
                                    
                                    error_messages.append(message)
                                    
                                    if level == 'ERROR':
                                        error_stats['total_errors'] += 1
                                    elif level == 'WARNING':
                                        error_stats['total_warnings'] += 1
                                        
                                    if log_time.date() == today:
                                        error_stats['today_errors'] += 1
                        except:
                            continue
        except Exception as e:
            logging.error(f"Error reading scheduler logs: {e}")
        
        # Find most common error
        if error_messages:
            most_common = Counter(error_messages).most_common(1)
            error_stats['most_common_error'] = most_common[0][0] if most_common else ''
        
        # If no database logs, try to read from file as fallback
        if not error_logs:
            try:
                import re
                log_file_path = 'app.log'
                
                with open(log_file_path, 'r') as f:
                    lines = f.readlines()
                    
                for line in lines[-1000:]:  # Only check last 1000 lines
                    match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ (\w+):(\w+):(.+)', line.strip())
                    if match:
                        timestamp_str, level, module, message = match.groups()
                        try:
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                            
                            if timestamp >= seven_days_ago and level in ['ERROR', 'WARNING']:
                                error_logs.append({
                                    'timestamp': timestamp,
                                    'level': level,
                                    'module': module,
                                    'message': message
                                })
                                
                                if level == 'ERROR':
                                    error_stats['total_errors'] += 1
                                elif level == 'WARNING':
                                    error_stats['total_warnings'] += 1
                                    
                                if timestamp.date() == today:
                                    error_stats['today_errors'] += 1
                                    
                        except ValueError:
                            continue
                            
                # Sort by timestamp descending
                error_logs.sort(key=lambda x: x['timestamp'], reverse=True)
                
            except FileNotFoundError:
                logging.warning("No error logs found in database or file")
        
        return render_template('error_logs.html', error_logs=error_logs, error_stats=error_stats)
        
    except Exception as e:
        logging.error(f"Error getting error logs: {e}")
        return render_template('error_logs.html', error_logs=[], error_stats={
            'total_errors': 0,
            'total_warnings': 0,
            'today_errors': 0,
            'most_common_error': str(e)
        })

@app.route('/api/reports/attendance_summary')
@login_required
def attendance_summary():
    try:
        from datetime import timedelta
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=6)

        daily_stats = []
        for i in range(7):
            current_date = start_date + timedelta(days=i)
            day_start = datetime.combine(current_date, datetime.min.time())
            day_end = datetime.combine(current_date, datetime.max.time())

            count = AttendanceLog.query.filter(
                AttendanceLog.timestamp >= day_start,
                AttendanceLog.timestamp <= day_end
            ).count()

            daily_stats.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'day': current_date.strftime('%a'),
                'count': count
            })

        return jsonify(daily_stats)
    except Exception as e:
        logging.error(f"Error getting attendance summary: {str(e)}")
        return jsonify([]), 500

@app.route('/api/reports/device_usage')
@login_required
def device_usage():
    try:
        from sqlalchemy import func
        device_stats = db.session.query(
            AttendanceLog.device_id,
            func.count(AttendanceLog.id).label('count')
        ).group_by(AttendanceLog.device_id).all()
        # Save settings to database
        for key, value in request.form.items():
            setting = AppSetting.query.filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                setting = AppSetting(key=key, value=value)
                db.session.add(setting)
        
        db.session.commit()
        
        # Restart scheduler to apply new settings
        try:
            from scheduler_health_monitor import SchedulerHealthMonitor
            monitor = SchedulerHealthMonitor()
            monitor.restart_scheduler()
            logging.info("Scheduler restarted with new settings")
        except Exception as scheduler_error:
            logging.error(f"Error restarting scheduler: {scheduler_error}")
        
        flash('Settings saved successfully!', 'success')
        
    except Exception as e:
        logging.error(f"Error saving settings: {str(e)}")
        flash(f'Error saving settings: {str(e)}', 'error')
    
    return redirect(url_for('settings')), 500

@app.route('/api/reports/status_breakdown')
@login_required
def status_breakdown():
    try:
        from sqlalchemy import func
        status_stats = db.session.query(
            AttendanceLog.status,
            func.count(AttendanceLog.id).label('count')
        ).group_by(AttendanceLog.status).all()

        result = [{
            'status': status,
            'count': count
        } for status, count in status_stats]

        return jsonify(result)
    except Exception as e:
        logging.error(f"Error getting status breakdown: {str(e)}")
        return jsonify([]), 500

@app.route('/api/reports/hourly_patterns')
@login_required
def hourly_patterns():
    try:
        from sqlalchemy import func, extract
        hourly_stats = db.session.query(
            extract('hour', AttendanceLog.timestamp).label('hour'),
            func.count(AttendanceLog.id).label('count')
        ).group_by(extract('hour', AttendanceLog.timestamp)).all()

        hours_data = [0] * 24
        for hour, count in hourly_stats:
            if hour is not None:
                hours_data[int(hour)] = count

        result = [{
            'hour': f'{i:02d}:00',
            'count': hours_data[i]
        } for i in range(24)]

        return jsonify(result)
    except Exception as e:
        logging.error(f"Error getting hourly patterns: {str(e)}")
        return jsonify([]), 500

@app.route('/api/reports/summary_stats')
@login_required
def summary_stats():
    try:
        today = datetime.utcnow().date()
        week_start = today - timedelta(days=7)
        
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        week_start_dt = datetime.combine(week_start, datetime.min.time())
        
        stats = {
            'today_logs': AttendanceLog.query.filter(
                AttendanceLog.timestamp >= today_start,
                AttendanceLog.timestamp <= today_end
            ).count(),
            'online_devices': Device.query.filter_by(online_status=True).count(),
            'total_users': User.query.filter_by(status='Active').count(),
            'week_logs': AttendanceLog.query.filter(
                AttendanceLog.timestamp >= week_start_dt
            ).count()
        }
        
        return jsonify(stats)
    except Exception as e:
        logging.error(f"Error getting summary stats: {str(e)}")
        return jsonify({'today_logs': 0, 'online_devices': 0, 'total_users': 0, 'week_logs': 0}), 500