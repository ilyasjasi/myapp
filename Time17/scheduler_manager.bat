@echo off
REM Scheduler Service Manager for Windows
REM Usage: scheduler_manager.bat [start|stop|restart|status]

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="restart" goto restart
if "%1"=="status" goto status
if "%1"=="" goto start
goto usage

:start
echo Starting Scheduler Service...
python start_scheduler.py start
if %ERRORLEVEL%==0 (
    echo Scheduler service started successfully
) else (
    echo Failed to start scheduler service
)
goto end

:stop
echo Stopping Scheduler Service...
python start_scheduler.py stop
if %ERRORLEVEL%==0 (
    echo Scheduler service stopped successfully
) else (
    echo Failed to stop scheduler service
)
goto end

:restart
echo Restarting Scheduler Service...
python start_scheduler.py restart
if %ERRORLEVEL%==0 (
    echo Scheduler service restarted successfully
) else (
    echo Failed to restart scheduler service
)
goto end

:status
python start_scheduler.py status
goto end

:usage
echo Usage: scheduler_manager.bat [start^|stop^|restart^|status]
echo.
echo Commands:
echo   start   - Start the scheduler service
echo   stop    - Stop the scheduler service
echo   restart - Restart the scheduler service
echo   status  - Check scheduler service status
echo.
echo If no command is provided, 'start' is used by default.

:end
pause
