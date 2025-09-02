from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from app import app, db
from models import *
from device_manager import DeviceManager
from utils import get_setting, set_setting
import logging

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
@login_required
def index():
    # Dashboard statistics
    total_devices = Device.query.count()
    online_devices = Device.query.filter_by(online_status=True).count()
    total_users = User.query.filter_by(status='Active').count()
    total_logs = AttendanceLog.query.count()
    
    # Today's logs
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    today_logs = AttendanceLog.query.filter(
        AttendanceLog.timestamp >= today_start,
        AttendanceLog.timestamp <= today_end
    ).count()
    
    # Yesterday's logs
    yesterday = today - timedelta(days=1)
    yesterday_start = datetime.combine(yesterday, datetime.min.time())
    yesterday_end = datetime.combine(yesterday, datetime.max.time())
    yesterday_logs = AttendanceLog.query.filter(
        AttendanceLog.timestamp >= yesterday_start,
        AttendanceLog.timestamp <= yesterday_end
    ).count()
    
    # Recent logs
    recent_logs = AttendanceLog.query.order_by(AttendanceLog.timestamp.desc()).limit(10).all()
    
    # Device status
    devices = Device.query.all()
    
    stats = {
        'total_devices': total_devices,
        'online_devices': online_devices,
        'total_users': total_users,
        'total_logs': total_logs,
        'today_logs': today_logs,
        'yesterday_logs': yesterday_logs
    }
    
    return render_template('index.html', stats=stats, recent_logs=recent_logs, devices=devices)

@app.route('/devices')
@login_required
def devices():
    devices = Device.query.all()
    areas = Area.query.all()
    return render_template('devices.html', devices=devices, areas=areas)

@app.route('/api/devices', methods=['POST'])
@login_required
def add_device():
    try:
        data = request.get_json()
        
        device = Device(
            device_id=data['device_id'],
            name=data['name'],
            ip_address=data['ip_address'],
            area_id=data.get('area_id')
        )
        
        db.session.add(device)
        db.session.commit()
        
        # Test connection and get device info
        device_info = device_manager.get_device_info(data['ip_address'])
        if device_info:
            device.mac_address = device_info.get('mac_address')
            device.serialnumber = device_info.get('serial_number')
            device.online_status = True
            db.session.commit()
        
        return jsonify({'success': True, 'message': 'Device added successfully'})
    except Exception as e:
        logging.error(f"Error adding device: {str(e)}")
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
        
        return jsonify({'success': True, 'message': 'Device updated successfully'})
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
    try:
        device = Device.query.get_or_404(device_id)
        logs_count = device_manager.sync_attendance_logs(device.ip_address, device.device_id)
        
        device.last_sync = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Synced {logs_count} logs'})
    except Exception as e:
        logging.error(f"Error syncing device: {str(e)}")
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
            online = device_manager.is_device_online(device.ip_address)
            device.online_status = online
            status_list.append({
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
                'online_status': online
            })
        
        db.session.commit()
        return jsonify(status_list)
    except Exception as e:
        logging.error(f"Error checking device status: {str(e)}")
        return jsonify([]), 500

@app.route('/users')
@login_required
def users():
    users = User.query.all()
    areas = Area.query.all()
    return render_template('users.html', users=users, areas=areas)

@app.route('/logs')
@login_required
def logs():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    logs = AttendanceLog.query.order_by(AttendanceLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('logs.html', logs=logs)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        csv_export_path = request.form.get('csv_export_path', '/tmp/ZKHours.csv')
        employee_csv_path = request.form.get('employee_csv_path', '/tmp/employees.csv')
        terminated_csv_path = request.form.get('terminated_csv_path', '/tmp/terminated.csv')
        csv_export_interval = request.form.get('csv_export_interval', '30')
        employee_sync_time = request.form.get('employee_sync_time', '00:00')
        
        set_setting('csv_export_path', csv_export_path)
        set_setting('employee_csv_path', employee_csv_path)
        set_setting('terminated_csv_path', terminated_csv_path)
        set_setting('csv_export_interval', csv_export_interval)
        set_setting('employee_sync_time', employee_sync_time)
        
        flash('Settings saved successfully', 'success')
        return redirect(url_for('settings'))
    
    settings = {
        'csv_export_path': get_setting('csv_export_path', '/tmp/ZKHours.csv'),
        'employee_csv_path': get_setting('employee_csv_path', '/tmp/employees.csv'),
        'terminated_csv_path': get_setting('terminated_csv_path', '/tmp/terminated.csv'),
        'csv_export_interval': get_setting('csv_export_interval', '30'),
        'employee_sync_time': get_setting('employee_sync_time', '00:00')
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

@app.route('/admin_users')
@login_required
def admin_users():
    users = AdminUser.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/api/admin_users', methods=['POST'])
@login_required
def add_admin_user():
    try:
        data = request.get_json()
        
        # Check if username already exists
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
        
        # Don't allow changing your own username or deleting yourself
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
        
        # Don't allow deleting yourself
        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot delete your own account'})
        
        # Don't allow deleting the last admin user
        if AdminUser.query.count() <= 1:
            return jsonify({'success': False, 'message': 'Cannot delete the last admin user'})
        
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Admin user deleted successfully'})
    except Exception as e:
        logging.error(f"Error deleting admin user: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Manual operation endpoints
@app.route('/api/manual/export_csv', methods=['POST'])
@login_required
def manual_export_csv():
    try:
        from scheduler import export_attendance_csv
        export_attendance_csv()
        return jsonify({'success': True, 'message': 'CSV export completed successfully'})
    except Exception as e:
        logging.error(f"Error in manual CSV export: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manual/sync_employees', methods=['POST'])
@login_required
def manual_sync_employees():
    try:
        from scheduler import sync_employee_data
        sync_employee_data()
        return jsonify({'success': True, 'message': 'Employee synchronization completed successfully'})
    except Exception as e:
        logging.error(f"Error in manual employee sync: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manual/process_terminated', methods=['POST'])
@login_required
def manual_process_terminated():
    try:
        from scheduler import process_terminated_employees
        count = process_terminated_employees()
        return jsonify({'success': True, 'message': f'Processed {count} terminated employees'})
    except Exception as e:
        logging.error(f"Error processing terminated employees: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manual/sync_all_devices', methods=['POST'])
@login_required
def manual_sync_all_devices():
    try:
        devices = Device.query.filter_by(online_status=True).all()
        synced_count = 0
        
        for device in devices:
            try:
                # Sync time
                if device_manager.sync_time_to_device(device.ip_address):
                    # Sync users
                    if device_manager.sync_users_to_device(device.ip_address, device.area_id):
                        synced_count += 1
            except Exception as e:
                logging.error(f"Error syncing device {device.name}: {str(e)}")
                continue
        
        return jsonify({'success': True, 'message': f'Synchronized {synced_count} devices'})
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
        devices = Device.query.filter_by(online_status=True).all()
        synced_count = 0
        
        for device in devices:
            try:
                if device_manager.sync_users_to_device(device.ip_address, device.area_id):
                    synced_count += 1
            except Exception as e:
                logging.error(f"Error syncing templates to device {device.name}: {str(e)}")
                continue
        
        return jsonify({'success': True, 'message': f'Synchronized biometric templates to {synced_count} devices'})
    except Exception as e:
        logging.error(f"Error syncing templates: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html')

@app.route('/api/reports/attendance_summary')
@login_required
def attendance_summary():
    try:
        # Get attendance data for the last 7 days
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
        # Get usage by device
        from sqlalchemy import func
        device_stats = db.session.query(
            AttendanceLog.device_id,
            func.count(AttendanceLog.id).label('count')
        ).group_by(AttendanceLog.device_id).all()
        
        result = []
        for device_id, count in device_stats:
            device = Device.query.filter_by(device_id=device_id).first()
            result.append({
                'device_id': device_id,
                'device_name': device.name if device else device_id,
                'count': count
            })
        
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error getting device usage: {str(e)}")
        return jsonify([]), 500

@app.route('/api/reports/status_breakdown')
@login_required
def status_breakdown():
    try:
        # Get breakdown by status
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
        # Get attendance patterns by hour
        from sqlalchemy import func, extract
        hourly_stats = db.session.query(
            extract('hour', AttendanceLog.timestamp).label('hour'),
            func.count(AttendanceLog.id).label('count')
        ).group_by(extract('hour', AttendanceLog.timestamp)).all()
        
        # Initialize 24-hour array
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
