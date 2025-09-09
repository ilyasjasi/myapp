# Scheduler Service Documentation

## Overview
The scheduler has been completely separated from the main Flask application to prevent crashes and ensure stability. The scheduler now runs as an independent service that can be managed separately.

## Architecture Changes

### Before (Problematic)
- Scheduler ran within Flask application thread
- Crashes affected entire application
- Resource conflicts between web app and scheduled jobs
- No isolation or recovery mechanisms

### After (Improved)
- **Independent Process**: Scheduler runs as separate Python process
- **Crash Isolation**: Scheduler crashes don't affect web application
- **Health Monitoring**: Automatic restart on failures
- **Resource Management**: Separate database connections and timeouts
- **Easy Management**: Simple start/stop commands

## Files Created

### 1. `scheduler_service.py`
- **Purpose**: Main scheduler service that runs independently
- **Features**:
  - Separate Flask context for database operations
  - Safe job wrappers with error handling
  - Configurable timeouts and limits
  - Comprehensive logging
  - Signal handling for clean shutdown

### 2. `start_scheduler.py`
- **Purpose**: Scheduler management script
- **Commands**:
  - `python start_scheduler.py start` - Start scheduler
  - `python start_scheduler.py stop` - Stop scheduler
  - `python start_scheduler.py restart` - Restart scheduler
  - `python start_scheduler.py status` - Check status

### 3. `scheduler_manager.bat`
- **Purpose**: Windows batch file for easy scheduler management
- **Usage**: Double-click or run `scheduler_manager.bat start`

### 4. `scheduler_health_monitor.py`
- **Purpose**: Monitors scheduler health and auto-restarts if needed
- **Features**:
  - Process monitoring
  - Health check validation
  - Automatic restart with cooldown
  - Restart attempt limits

## Usage Instructions

### Starting the Application
1. **Start Flask App**: `python main.py`
2. **Start Scheduler**: `python start_scheduler.py start`
3. **Optional - Start Monitor**: `python scheduler_health_monitor.py`

### Managing the Scheduler

#### Using Python Scripts
```bash
# Start scheduler
python start_scheduler.py start

# Check status
python start_scheduler.py status

# Stop scheduler
python start_scheduler.py stop

# Restart scheduler
python start_scheduler.py restart
```

#### Using Windows Batch File
```cmd
# Start scheduler
scheduler_manager.bat start

# Check status
scheduler_manager.bat status

# Stop scheduler
scheduler_manager.bat stop

# Restart scheduler
scheduler_manager.bat restart
```

### Health Monitoring
```bash
# Start health monitor (runs continuously)
python scheduler_health_monitor.py
```

## Scheduled Jobs

### 1. CSV Export
- **Frequency**: Every 30 minutes (configurable)
- **Function**: Exports attendance logs to CSV
- **Safety**: Batch processing with limits

### 2. Employee Import
- **Frequency**: Daily at 00:00 (configurable)
- **Function**: Imports employee data from CSV
- **Safety**: Row-by-row processing with error handling

### 3. Employee Termination
- **Frequency**: Daily at 01:00 (configurable)
- **Function**: Processes terminated employees
- **Safety**: Individual record processing

### 4. Device Sync
- **Frequency**: Every 5 minutes (configurable)
- **Function**: Syncs data from devices
- **Safety**: Limited to 3 devices per run, 20-second timeout

### 5. Health Check
- **Frequency**: Every 5 minutes
- **Function**: Confirms scheduler is responsive
- **Safety**: Simple logging operation

## Configuration

Job settings are loaded from the database `Setting` table:
- `csv_export_interval`: Minutes between CSV exports (default: 30)
- `employee_sync_time`: Time for employee import (default: "00:00")
- `terminate_sync_time`: Time for termination processing (default: "01:00")
- `device_sync_interval`: Minutes between device syncs (default: 5)
- `csv_export_path`: Path for CSV exports
- `employee_csv_path`: Path for employee import CSV
- `terminated_csv_path`: Path for termination CSV

## Logging

### Scheduler Service Logs
- **File**: `scheduler_service.log`
- **Format**: Timestamped with job details
- **Rotation**: Manual (consider implementing log rotation)

### Health Monitor Logs
- **File**: `scheduler_monitor.log`
- **Format**: Timestamped monitoring events
- **Content**: Health checks, restarts, errors

## Safety Features

### 1. Process Isolation
- Scheduler crashes don't affect Flask app
- Separate memory space and resources
- Independent database connections

### 2. Error Handling
- Job-level error catching and logging
- Database transaction rollback on errors
- Graceful degradation on failures

### 3. Resource Limits
- Device sync limited to 3 devices per run
- 20-second timeout per device operation
- Batch processing for large datasets

### 4. Restart Protection
- Cooldown period between restarts (5 minutes)
- Maximum restart attempts (3)
- Health check validation before considering healthy

### 5. Signal Handling
- Graceful shutdown on SIGINT/SIGTERM
- Proper cleanup of resources
- PID file management

## Troubleshooting

### Scheduler Won't Start
1. Check if already running: `python start_scheduler.py status`
2. Check logs: `scheduler_service.log`
3. Verify database connectivity
4. Check file permissions

### Jobs Not Running
1. Verify scheduler is running: `python start_scheduler.py status`
2. Check job configuration in database
3. Review `scheduler_service.log` for errors
4. Restart scheduler: `python start_scheduler.py restart`

### Application Still Crashes
1. Verify scheduler is running separately
2. Check Flask app logs for non-scheduler issues
3. Ensure no old scheduler code in Flask app
4. Restart both services independently

### Performance Issues
1. Monitor device sync frequency
2. Check CSV export batch sizes
3. Review database connection pool settings
4. Consider reducing job frequencies

## Migration Notes

### Changes Made to Existing Files

#### `main.py`
- Removed scheduler initialization
- Removed auto-sync thread
- Added note about separate scheduler service

#### `app.py`
- Added logging about scheduler separation
- Kept background tasks for device monitoring only

### Backward Compatibility
- All existing job functions preserved
- Database schema unchanged
- Configuration settings maintained
- Job execution logging continues

## Best Practices

### 1. Always Use Service Management
- Don't run `scheduler_service.py` directly
- Use `start_scheduler.py` for proper process management
- Monitor with health monitor for production

### 2. Monitor Logs Regularly
- Check `scheduler_service.log` for job status
- Review `scheduler_monitor.log` for health issues
- Set up log rotation for long-term operation

### 3. Test Configuration Changes
- Stop scheduler before changing settings
- Verify settings in database
- Restart and monitor first few job executions

### 4. Backup Strategy
- Include scheduler logs in backups
- Test scheduler restart procedures
- Document custom configuration changes

## Production Deployment

### 1. Service Installation
Consider installing as Windows service or systemd service for automatic startup

### 2. Monitoring Integration
- Integrate with existing monitoring systems
- Set up alerts for scheduler failures
- Monitor job execution times and success rates

### 3. Log Management
- Implement log rotation
- Set up centralized logging if needed
- Monitor disk space usage

### 4. Security Considerations
- Run scheduler with minimal required permissions
- Secure log files and PID files
- Regular security updates for dependencies
